from selenium.webdriver.chrome.service import Service as ChromeService
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def open_in_new_tab_and_switch(driver, url, wait_seconds=10):
    current_handles = driver.window_handles[:]
    driver.execute_script("window.open(arguments[0], '_blank');", url)
    WebDriverWait(driver, wait_seconds).until(lambda d: len(d.window_handles) > len(current_handles))
    driver.switch_to.window(driver.window_handles[-1])

def slow_scroll_until_visible(driver, css_selector, max_attempts=20, pause=0.8, step_ratio=3):
    """
    Sayfayı yavaşça aşağı kaydırarak css_selector görünen hale gelene kadar bekler.
    step_ratio=3 ise her adımda pencere yüksekliğinin 1/3'ü kadar kaydırır.
    """
    for _ in range(max_attempts):
        driver.execute_script(f"window.scrollBy(0, Math.floor(window.innerHeight/{step_ratio}));")
        try:
            elem = driver.find_element(By.CSS_SELECTOR, css_selector)
            if elem.is_displayed():
                return True
        except:
            pass
        time.sleep(pause)
    return False

def get_breadcrumb_texts(driver):
    """
    Sayfanın üstündeki breadcrumb (kategori yolu) metinlerini döndürür.
    Önce kullanıcı tarafından verilen spesifik selector denenir, sonra fallback selector'lar.
    """
    preferred = [
        "#product-detail-seo-main-breadcrumbs > div.breadcrumb-wrapper > ul > li > a",
    ]
    fallbacks = [
        "nav.breadcrumb a",
        "ol.breadcrumb li a",
        ".breadcrumb a",
        "nav[aria-label='breadcrumb'] a",
        ".breadcrumbs a",
        ".product-breadcrumb a",
        "nav[role='navigation'] .breadcrumb a",
    ]
    for sel in preferred + fallbacks:
        elems = driver.find_elements(By.CSS_SELECTOR, sel)
        texts = [e.text.strip() for e in elems if e.text.strip()]
        if texts:
            return texts
    return []

def filter_breadcrumbs(crumbs, title_text):
    """
    Breadcrumb listesinden 1) Anasayfa/Home, 2) Marka, 3) Son (ürün adı) öğelerini çıkarır.
    Geriye kategoriler kalır (ör: Elektronik > Klima Isıtıcı > Vantilatör).
    """
    if not crumbs:
        return []

    # Eğer beklenen yapıdaysa (>=3 öğe), doğrudan index bazlı filtre uygula
    # 0: Anasayfa, 1: Marka, 2..-2: Kategoriler, -1: Ürün
    if len(crumbs) >= 3:
        # Bazı sayfalarda ürün ek öğe olarak olmayabilir; güvenli dilimleme yapıyoruz
        core = crumbs[:]
        # Ürün (son) çıkar
        core = core[:-1] if len(core) >= 1 else core
        # Marka (ikinci) çıkar
        if len(core) >= 2:
            del core[1]
        # Anasayfa (ilk) çıkar
        if len(core) >= 1:
            del core[0]
        return core

    # Fallback: önceki genel mantık
    items = [c for c in crumbs if c and c.lower() not in ("anasayfa", "home")]  # Home çıkar
    if len(items) >= 2:
        items = items[:-1]  # ürünü çıkar
    brand_guess = (title_text.split()[0] if title_text else "").strip()
    filtered = [c for c in items if not brand_guess or c.lower() != brand_guess.lower()]
    # Tekrarlananları kaldır (sıra korunur)
    seen = set()
    result = []
    for c in filtered:
        if c not in seen:
            seen.add(c)
            result.append(c)
    return result

def get_text_or(driver, by, selector, timeout=6, default=""):
    try:
        elem = WebDriverWait(driver, timeout).until(EC.presence_of_element_located((by, selector)))
        return elem.text
    except:
        return default

def visit_products(category_url: str, headless: bool = True) -> None:
    """
    Verilen kategori sayfasındaki ürün bağlantılarını bulur ve her bir ürün sayfasını
    sırayla açıp hemen geri döner. headless=False yapılırsa Chrome penceresi açılır.
    """
    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    if headless:
        options.add_argument("--headless")  # arka planda çalışması için

    # ChromeDriver'ı sistemde bulmak veya indirmek için webdriver_manager kullanıyoruz
    service = ChromeService(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    try:
        # Kategori sayfasına git
        driver.get(category_url)
        time.sleep(3)  # sayfanın yüklenmesini bekle

        # Liste konteynerinin yüklendiğini garanti et
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.srch-prdcts-cntnr")))
        main_window = driver.current_window_handle

        index = 1
        consecutive_failures = 0
        max_failures = 10

        while consecutive_failures < max_failures:
            # 1) Ana sayfada sıradaki ürünün linkini al
            selector = f"#search-app > div > div > div > div.srch-prdcts-cntnr.srch-prdcts-cntnr-V2.search-products-container-for-blacklistUrl > div:nth-child(4) > div:nth-child(1) > div > div:nth-child({index}) > a"
            try:
                elem = driver.find_element(By.CSS_SELECTOR, selector)
                href = elem.get_attribute("href")
                if href and href.startswith("/"):
                    href = "https://www.trendyol.com" + href

                # 2) Ürünü yeni sekmede aç ve ürüne geç
                open_in_new_tab_and_switch(driver, href)
                # Ürün başlığı görününceye kadar bekle
                title = get_text_or(driver, By.CSS_SELECTOR, "#envoy > div > h1", timeout=10, default="Başlık bulunamadı")

                # 3) Başlık, fiyat, puan (ilk olarak bunlar)
                price = get_text_or(driver, By.CLASS_NAME, "price-view-original", timeout=6, default="")
                if not price or price == "Fiyat bulunamadı":
                    price = get_text_or(driver, By.CSS_SELECTOR, "#envoy > div > div.tooltip-wrapper > div > div.price-view > span.discounted", timeout=6, default="")
                if not price or price == "Fiyat bulunamadı":
                    price = get_text_or(driver, By.CSS_SELECTOR, "#envoy > div > div.price.normal-price > div > span", timeout=6, default="Fiyat bulunamadı")
                rating = get_text_or(driver, By.CSS_SELECTOR, "#envoy > div > div.product-details-other-details > div > div > div > span", timeout=6, default="Puan bulunamadı")

                print("Başlık:", title)
                print("Fiyat:", price)
                print("Puan:", rating)
                # --- Kategoriler (breadcrumb) ---
                breadcrumb_all = get_breadcrumb_texts(driver)
                categories = filter_breadcrumbs(breadcrumb_all, title)
                if categories:
                    print("Kategoriler:", " > ".join(categories))
                else:
                    print("Kategoriler: bulunamadı")
                print("-"*20)

                # 4) Yorumlar başlığı bulunana kadar yavaş kaydır
                found_reviews = slow_scroll_until_visible(driver, 'h2[data-testid="reviews-header"]', max_attempts=15, pause=1.0, step_ratio=2)

                # 5) Yorumları yeni sekmede aç, içeri gir ve tüm yorumları yazdır
                if found_reviews:
                    try:
                        show_comments_button = driver.find_element(By.CSS_SELECTOR, 'a[data-testid="show-more-button"]')
                        comments_link = show_comments_button.get_attribute("href")
                        open_in_new_tab_and_switch(driver, comments_link)
                        # Yorumlar yüklenene kadar bekle
                        WebDriverWait(driver, 10).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.comment-text > p")))
                        comments = driver.find_elements(By.CSS_SELECTOR, "div.comment-text > p")
                        for comment in comments:
                            if comment.text.strip():
                                print("Yorum:", comment.text.strip())
                        # Yorum sekmesini kapat ve ürün sekmesine dön
                        driver.close()
                        driver.switch_to.window(driver.window_handles[-1])  # ürün sekmesi
                    except Exception as e:
                        print("Yorumlar alınamadı:", e)
                else:
                    print("Ürün değerlendirmeleri başlığı bulunamadı.")

                # 6) Soru-cevap butonu görünene kadar yavaş kaydır (yorumlar sonrası genelde görünüyor)
                found_qa_button = slow_scroll_until_visible(driver, 'a[data-testid="show-more-button"][href*="saticiya-sor"]', max_attempts=15, pause=1.0, step_ratio=2)

                # 7) Soru-cevap sekmesini aç, içeri gir ve verileri yazdır
                if found_qa_button:
                    try:
                        qa_button = driver.find_element(By.CSS_SELECTOR, 'a[data-testid="show-more-button"][href*="saticiya-sor"]')
                        qa_link = qa_button.get_attribute("href")
                        open_in_new_tab_and_switch(driver, qa_link)

                        # Bloklar yüklenene kadar bekle
                        WebDriverWait(driver, 10).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.pr-qna-v2 > div > div > div")))
                        qa_blocks = driver.find_elements(By.CSS_SELECTOR, "div.pr-qna-v2 > div > div > div")
                        for block in qa_blocks:
                            try:
                                question = block.find_element(By.CSS_SELECTOR, "div.item > div > h4").text
                            except:
                                question = "Soru bulunamadı"
                            try:
                                answer = block.find_element(By.CSS_SELECTOR, "div.answer > div:nth-child(2) > h5").text
                            except:
                                answer = "Cevap bulunamadı"
                            print("Soru:", question)
                            print("Cevap:", answer)
                            print("-" * 20)

                        # Q&A sekmesini kapat ve ürün sekmesine dön
                        driver.close()
                        driver.switch_to.window(driver.window_handles[-1])  # ürün sekmesi
                    except Exception as e:
                        print("Soru-Cevap bölümü alınamadı:", e)
                else:
                    print("Soru-Cevap butonu bulunamadı.")

                print("-" * 50)

                # 8) Ürün sekmesini kapat ve ana sayfaya dön
                driver.close()
                driver.switch_to.window(main_window)

                # her 4 üründen sonra ana listede az kaydır (575px)
                if index % 4 == 0:
                    driver.execute_script("window.scrollBy(0, 575);")
                    time.sleep(1)

                time.sleep(1.5)
                index += 1
                consecutive_failures = 0

            except Exception as e:
                # Hata durumunda tüm alt sekmeleri kapatıp ana sayfaya dön
                print("Hata:", e)
                # Açık başka sekme varsa kapat
                while len(driver.window_handles) > 1:
                    try:
                        driver.switch_to.window(driver.window_handles[-1])
                        driver.close()
                    except:
                        break
                # Ana pencereye dön
                try:
                    driver.switch_to.window(main_window)
                except:
                    pass
                consecutive_failures += 1
                # Ana listede hafif kaydır ve tekrar dene
                driver.execute_script("window.scrollBy(0, 575);")
                time.sleep(1)

    finally:
        driver.quit()

# Örnek kullanım
if __name__ == "__main__":
    # headless=False yaparsanız tarayıcı penceresi açılır ve adımları görebilirsiniz.
    visit_products("https://www.trendyol.com/sr?wc=104024&sst=BEST_SELLER", headless=False)