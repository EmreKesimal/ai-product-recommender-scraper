from selenium.webdriver.chrome.service import Service as ChromeService
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import time
from selenium.webdriver.common.by import By

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

        # Sayfa kaynağını BeautifulSoup ile parse et
        soup = BeautifulSoup(driver.page_source, "html.parser")
        product_links = []
        for card in soup.find_all("div", class_="widget-product"):
            a_tag = card.find("a", href=True)
            if a_tag:
                product_links.append("https://www.trendyol.com" + a_tag["href"])

        # Her ürün sayfasını sırayla aç ve geri dön
        for link in product_links:
            driver.get(link)
            time.sleep(2)  # ürün sayfasının yüklenmesini bekle

            try:
                price = driver.find_element(By.CLASS_NAME, "price-view-original").text
            except:
                price = "Fiyat bulunamadı"

            try:
                title = driver.find_element(By.CSS_SELECTOR, "#envoy > div > h1").text
            except:
                title = "Başlık bulunamadı"

            try:
                rating = driver.find_element(By.CSS_SELECTOR, "#envoy > div > div.product-details-other-details > div > div > div > span").text
            except:
                rating = "Puan bulunamadı"

            print("Başlık:", title)
            print("Fiyat:", price)
            print("Puan:", rating)
            print("-" * 50)

            try:
                # Scroll until the "Ürün Değerlendirmeleri" başlığı görünür olana kadar
                SCROLL_PAUSE_TIME = 1.0
                max_scroll_attempts = 15
                scroll_attempt = 0
                reviews_header_found = False

                while scroll_attempt < max_scroll_attempts:
                    driver.execute_script("window.scrollBy(0, window.innerHeight / 2);")
                    time.sleep(SCROLL_PAUSE_TIME)

                    try:
                        reviews_header = driver.find_element(By.CSS_SELECTOR, 'h2[data-testid="reviews-header"]')
                        if reviews_header.is_displayed():
                            reviews_header_found = True
                            break
                    except:
                        pass

                    scroll_attempt += 1

                if not reviews_header_found:
                    print("Ürün değerlendirmeleri başlığı bulunamadı.")
                    continue  # yorumları atla ve diğer ürüne geç

                # Header bulundu, şimdi yorumlar butonunu bul ve devam et
                show_comments_button = driver.find_element(By.CSS_SELECTOR, 'a[data-testid="show-more-button"]')

                show_comments_link = show_comments_button.get_attribute("href")
                driver.execute_script("window.open(arguments[0]);", show_comments_link)
                driver.switch_to.window(driver.window_handles[1])
                time.sleep(3)

                comments = driver.find_elements(By.CSS_SELECTOR, "div.comment-text > p")
                for comment in comments:
                    print("Yorum:", comment.text)

                driver.close()
                driver.switch_to.window(driver.window_handles[0])

            except Exception as e:
                print("Yorumlar alınamadı:", e)

            # --- Soru-Cevap (Q&A) bölümü ekle ---
            try:
                # Scroll to reveal "Tüm Soruları Göster" button
                SCROLL_PAUSE_TIME = 1.0
                max_scroll_attempts = 15
                scroll_attempt = 0
                questions_header_found = False

                while scroll_attempt < max_scroll_attempts:
                    driver.execute_script("window.scrollBy(0, window.innerHeight / 2);")
                    time.sleep(SCROLL_PAUSE_TIME)

                    try:
                        questions_button = driver.find_element(By.CSS_SELECTOR, 'a[data-testid="show-more-button"][href*="saticiya-sor"]')
                        if questions_button.is_displayed():
                            questions_header_found = True
                            break
                    except:
                        pass

                    scroll_attempt += 1

                if not questions_header_found:
                    print("Soru-Cevap butonu bulunamadı.")
                    continue  # diğer ürüne geç

                # Soru-Cevap sayfasını aç
                questions_link = questions_button.get_attribute("href")
                driver.execute_script("window.open(arguments[0]);", questions_link)
                driver.switch_to.window(driver.window_handles[1])
                time.sleep(3)

                # Soruları ve cevapları yazdır
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

                driver.close()
                driver.switch_to.window(driver.window_handles[0])

            except Exception as e:
                print("Soru-Cevap bölümü alınamadı:", e)

            driver.back()
            time.sleep(1)  # geri dönüş sonrası kategori sayfasının yüklenmesini bekle

    finally:
        driver.quit()

# Örnek kullanım
if __name__ == "__main__":
    # headless=False yaparsanız tarayıcı penceresi açılır ve adımları görebilirsiniz.
    visit_products("https://www.trendyol.com/butik/liste/5/elektronik", headless=False)