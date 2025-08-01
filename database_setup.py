from pymongo import MongoClient, ASCENDING, TEXT
from pymongo.errors import OperationFailure

# MongoDB Atlas bağlantı bilgileriniz
MONGO_URI = "mongodb+srv://scraper4253:yamandede403@cluster0.cv576qm.mongodb.net/scrapingdb?retryWrites=true&w=majority&appName=Cluster0"
DATABASE_NAME = "scrapingdb"
COLLECTION_NAME = "products"


def create_indexes():
    """
    AI sorgularını optimize etmek için MongoDB koleksiyonuna gerekli indeksleri oluşturur.
    Bu script'i scraper'ı çalıştırmadan önce sadece bir kez çalıştırmanız yeterlidir.
    """
    try:
        print("MongoDB'ye bağlanılıyor...")
        client = MongoClient(MONGO_URI)
        db = client[DATABASE_NAME]
        collection = db[COLLECTION_NAME]
        print("Bağlantı başarılı.")

        print("İndeksler oluşturuluyor...")

        # 1. Ürün URL'sinin benzersiz olmasını sağla (duplikasyon önleme)
        collection.create_index([("product_url", ASCENDING)], unique=True, name="product_url_unique")
        print("- product_url için benzersiz indeks oluşturuldu.")

        # 2. Marka ve kategoriye göre hızlı filtreleme için indeksler
        collection.create_index([("brand", ASCENDING)], name="brand_index")
        print("- brand için indeks oluşturuldu.")
        collection.create_index([("categories", ASCENDING)], name="categories_index")
        print("- categories için indeks oluşturuldu.")

        # 3. Fiyat ve puana göre hızlı sıralama/filtreleme için indeksler
        collection.create_index([("price.current", ASCENDING)], name="price_index")
        print("- price.current için indeks oluşturuldu.")
        collection.create_index([("rating", ASCENDING)], name="rating_index")
        print("- rating için indeks oluşturuldu.")

        # 4. Yorum ve başlık içinde metin araması için TEXT indeksi (AI için çok önemli)
        collection.create_index(
            [("title", TEXT), ("reviews", TEXT)],
            name="text_search_index",
            default_language='turkish'
        )
        print("- title ve reviews için metin arama indeksi oluşturuldu.")

        print("\nTüm indeksler başarıyla oluşturuldu veya zaten mevcuttu.")

    except OperationFailure as e:
        print(f"Bir indeks operasyonu hatası oluştu: {e.details}")
    except Exception as e:
        print(f"Bir hata oluştu: {e}")
    finally:
        if 'client' in locals():
            client.close()
            print("MongoDB bağlantısı kapatıldı.")


if __name__ == "__main__":
    create_indexes()
