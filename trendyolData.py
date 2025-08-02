import os
import json
import re
from datetime import datetime
import time
from pymongo import MongoClient
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# --- Konfigürasyon ve Veritabanı Bağlantısı ---
MONGO_URI = "mongodb+srv://scraper4253:yamandede403@cluster0.cv576qm.mongodb.net/scrapingdb?retryWrites=true&w=majority&appName=Cluster0"
client = MongoClient(MONGO_URI)
db = client.scrapingdb
products_collection = db.products


# --- Yardımcı Fonksiyonlar ---

def open_in_new_tab_and_switch(driver, url, wait_seconds=10):
    """Verilen URL'yi yeni sekmede açar ve o sekmeye geçer."""
    current_handles = driver.window_handles[:]
    driver.execute_script("window.open(arguments[0], '_blank');", url)
    WebDriverWait(driver, wait_seconds).until(lambda d: len(d.window_handles) > len(current_handles))
    driver.switch_to.window(driver.window_handles[-1])


def slow_scroll_until_visible(driver, css_selector, max_attempts=20, pause=0.8, step_ratio=3):
    """Sayfayı yavaşça aşağı kaydırarak belirli bir element görünür olana kadar bekler."""
    for _ in range(max_attempts):
        driver.execute_script(f"window.scrollBy(0, Math.floor(window.innerHeight/{step_ratio}));")
        try:
            elem = driver.find_element(By.CSS_SELECTOR, css_selector)
            if elem.is_displayed(): return True
        except:
            pass
        time.sleep(pause)
    return False


def get_text_or(driver, by, selector, timeout=6, default=""):
    """Belirtilen elementi bulup metnini döndürür, bulamazsa varsayılan değeri döndürür."""
    try:
        elem = WebDriverWait(driver, timeout).until(EC.presence_of_element_located((by, selector)))
        return elem.text.strip()
    except:
        return default


def get_attribute_or(driver, by, selector, attribute, timeout=6, default=""):
    """Belirtilen elementin belirtilen özelliğini döndürür, bulamazsa varsayılan değeri döndürür."""
    try:
        elem = WebDriverWait(driver, timeout).until(EC.presence_of_element_located((by, selector)))
        return elem.get_attribute(attribute)
    except:
        return default


def transform_data_for_db(data):
    """Scraper'dan gelen ham veriyi veritabanı şemasına uygun hale getirir."""
    price_numeric = 0.0
    if data.get("price") and data["price"] != "Fiyat bulunamadı":
        match = re.search(r'[\d\.,]+', data["price"].replace('.', '').replace(',', '.'))
        if match: price_numeric = float(match.group(0))

    rating_numeric = 0.0
    if data.get("rating") and data["rating"] != "Puan bulunamadı":
        try:
            rating_numeric = float(data["rating"])
        except (ValueError, TypeError):
            pass

    # GÜNCELLENDİ: Değerlendirme sayısını metinden daha güvenilir ayıkla
    rating_count_numeric = 0
    if data.get("rating_count"):
        # "95 Değerlendirme" veya "1.245 Değerlendirme" gibi metinlerden sadece sayıyı alır
        numbers_only = re.sub(r'[^\d]', '', data["rating_count"])
        if numbers_only:
            rating_count_numeric = int(numbers_only)

    brand = data["title"].split()[0] if data.get("title") and data["title"] != "Başlık bulunamadı" else "Bilinmiyor"

    image_list = []
    if data.get("image_url"):
        image_list.append(data["image_url"])

    return {
        "product_url": data["url"],
        "title": data["title"],
        "brand": brand,
        "price": {"current": price_numeric, "currency": "TL"},
        "rating": rating_numeric,
        "rating_count": rating_count_numeric,  # Veritabanı şemasına eklendi
        "categories": data.get("categories", []),
        "images": image_list,
        "features": data.get("features", {}),
        "reviews": data.get("reviews", []),
        "qa": data.get("qa", []),
        "scraped_at": datetime.utcnow()
    }


# --- Ana Scraper Fonksiyonu ---

def visit_products(category_url: str, headless: bool = True) -> None:
    """Verilen kategori sayfasındaki ürünleri gezer ve bilgilerini toplar."""
    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    # Headless modda scraper'ların tespit edilmesini zorlaştırmak için ayarlar
    options.add_argument("window-size=1920,1080")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36")

    if headless:
        options.add_argument("--headless")

    service = ChromeService(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    try:
        driver.get(category_url)
        time.sleep(2)  # Sayfanın ilk JavaScript'lerinin çalışması için bekleme

        try:
            WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))).click()
            print("Çerezler kabul edildi.")
        except TimeoutException:
            print("Çerez butonu bulunamadı veya zaten kabul edilmiş.")

        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.srch-prdcts-cntnr")))
        main_window = driver.current_window_handle

        index = 1
        consecutive_failures = 0
        max_failures = 10

        while consecutive_failures < max_failures:
            print(f"\n--- Ürün Index {index} işleniyor ---")
            product_selector = f"#search-app > div > div > div > div.srch-prdcts-cntnr.srch-prdcts-cntnr-V2.search-products-container-for-blacklistUrl > div:nth-child(4) > div:nth-child(1) > div > div:nth-child({index}) > a"

            try:
                elem = driver.find_element(By.CSS_SELECTOR, product_selector)
                href = elem.get_attribute("href")
                if href and href.startswith("/"): href = "https://www.trendyol.com" + href

                open_in_new_tab_and_switch(driver, href)

                raw_product_data = {"url": href}

                raw_product_data["title"] = get_text_or(driver, By.CSS_SELECTOR, "#envoy > div > h1", timeout=10,
                                                        default="Başlık bulunamadı")
                raw_product_data["rating"] = get_text_or(driver, By.CSS_SELECTOR,
                                                         "#envoy > div > div.product-details-other-details > div > div > div > span",
                                                         timeout=6, default="Puan bulunamadı")

                # GÜNCELLENDİ: Değerlendirme sayısını daha güvenilir bir seçici ile çek
                raw_product_data["rating_count"] = get_text_or(driver, By.CSS_SELECTOR,
                                                               "a[data-testid='review-info-link']", timeout=6,
                                                               default="0")

                raw_product_data["image_url"] = get_attribute_or(driver, By.CSS_SELECTOR, "img[data-testid='image']",
                                                                 "src", default="")

                price_selectors = ["#envoy > div > div.tooltip-wrapper > div > div.price-view > span.discounted",
                                   "#envoy > div > div.tooltip-wrapper > div > div.price-view > span",
                                   "#envoy > div > div.price.campaign-price > div.campaign-price-content > p.new-price",
                                   "#envoy > div > div.price.normal-price > div > span"]
                price = "Fiyat bulunamadı"
                for sel in price_selectors:
                    try:
                        price = driver.find_element(By.CSS_SELECTOR, sel).text
                        if price: break
                    except:
                        continue
                raw_product_data["price"] = price

                breadcrumb_all = [e.text.strip() for e in
                                  driver.find_elements(By.CSS_SELECTOR, "#product-detail-seo-main-breadcrumbs a") if
                                  e.text.strip()]
                raw_product_data["categories"] = breadcrumb_all[1:-1] if len(breadcrumb_all) > 2 else breadcrumb_all

                raw_product_data["reviews"] = []
                if slow_scroll_until_visible(driver, 'a[data-testid="show-more-button"][href*="/yorumlar"]',
                                             max_attempts=15, pause=1.0):
                    try:
                        comments_link = driver.find_element(By.CSS_SELECTOR,
                                                            'a[data-testid="show-more-button"][href*="/yorumlar"]').get_attribute(
                            "href")
                        open_in_new_tab_and_switch(driver, comments_link)
                        print("Daha fazla yorum yükleniyor...")
                        for _ in range(5):
                            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                            time.sleep(1.5)
                        comments = driver.find_elements(By.CSS_SELECTOR, "div.comment-text > p")
                        raw_product_data["reviews"] = [c.text.strip() for c in comments if c.text.strip()]
                        driver.close()
                        driver.switch_to.window(driver.window_handles[-1])
                    except Exception as e:
                        print(f"Yorumlar alınamadı: {e}")

                raw_product_data["qa"] = []
                if slow_scroll_until_visible(driver, 'a[data-testid="show-more-button"][href*="saticiya-sor"]',
                                             max_attempts=15, pause=1.0):
                    try:
                        qa_link = driver.find_element(By.CSS_SELECTOR,
                                                      'a[data-testid="show-more-button"][href*="saticiya-sor"]').get_attribute(
                            "href")
                        open_in_new_tab_and_switch(driver, qa_link)
                        WebDriverWait(driver, 10).until(
                            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.pr-qna-v2 > div > div > div")))
                        qa_blocks = driver.find_elements(By.CSS_SELECTOR, "div.pr-qna-v2 > div > div > div")
                        for block in qa_blocks:
                            question = get_text_or(block, By.CSS_SELECTOR, "div.item > div > h4",
                                                   default="Soru bulunamadı")
                            answer = get_text_or(block, By.CSS_SELECTOR, "div.answer > div:nth-child(2) > h5",
                                                 default="Cevap bulunamadı")
                            raw_product_data["qa"].append({"question": question, "answer": answer})
                        driver.close()
                        driver.switch_to.window(driver.window_handles[-1])
                    except Exception as e:
                        print(f"Soru-Cevap bölümü alınamadı: {e}")

                raw_product_data["features"] = {}
                try:
                    slow_scroll_until_visible(driver, "#product-attributes", max_attempts=10, pause=0.5)
                    feature_items = driver.find_elements(By.CSS_SELECTOR, "div.attribute-item")
                    for item in feature_items:
                        try:
                            key = item.find_element(By.CSS_SELECTOR, ".name").text.strip()
                            value = item.find_element(By.CSS_SELECTOR, ".value").text.strip()
                            if key and value: raw_product_data["features"][key] = value
                        except NoSuchElementException:
                            continue
                except Exception as e:
                    print(f"Ürün özellikleri alınamadı: {e}")

                db_document = transform_data_for_db(raw_product_data)

                products_collection.update_one(
                    {"product_url": db_document["product_url"]},
                    {"$set": db_document},
                    upsert=True
                )
                print(f"'{db_document['title']}' ürünü başarıyla veritabanına kaydedildi/güncellendi.")
                print("-" * 50)

                driver.close()
                driver.switch_to.window(main_window)

                if index % 4 == 0:
                    print(f"--- 4'lü grup tamamlandı. Yeni ürünler için sayfa kaydırılıyor... ---")
                    driver.execute_script("window.scrollBy(0, 575);")
                    time.sleep(2)

                index += 1
                consecutive_failures = 0

            except Exception as e:
                print(f"Hata (index {index}): {e}")
                consecutive_failures += 1
                while len(driver.window_handles) > 1:
                    driver.switch_to.window(driver.window_handles[-1])
                    driver.close()
                try:
                    driver.switch_to.window(main_window)
                except:
                    pass
                index += 1
                driver.execute_script("window.scrollBy(0, 200);")
                time.sleep(1)

    finally:
        print("Scraper tamamlandı.")
        client.close()
        driver.quit()


if __name__ == "__main__":
    # Örnek bir kategori URL'si
    TARGET_URL = "https://www.trendyol.com/sr?q=kulakl%C4%B1k&qt=kulakl%C4%B1k&st=kulakl%C4%B1k&os=1"
    # headless=True yaparak arka planda çalıştırabilirsiniz
    visit_products(TARGET_URL, headless=False)
