import requests
import json
import time
import random
import unicodedata
import gdown
import os
import logging
import sys
import pickle
from datetime import datetime
from bs4 import BeautifulSoup
from headerler import headers, grok_headers

# Loglama ayarları
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("tweet_program.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Program durumunu kaydetme ve yükleme fonksiyonları
def save_state(state):
    """Program durumunu kaydeder."""
    try:
        with open("program_state.pkl", "wb") as f:
            pickle.dump(state, f)
        logger.info("Program durumu başarıyla kaydedildi.")
    except Exception as e:
        logger.error(f"Program durumu kaydedilemedi: {e}")

def load_state():
    """Kaydedilmiş program durumunu yükler."""
    try:
        if os.path.exists("program_state.pkl"):
            with open("program_state.pkl", "rb") as f:
                state = pickle.load(f)
            logger.info("Program durumu başarıyla yüklendi.")
            return state
        else:
            logger.info("Kaydedilmiş program durumu bulunamadı. Yeni başlangıç yapılıyor.")
            return None
    except Exception as e:
        logger.error(f"Program durumu yüklenemedi: {e}")
        return None

# İnternet bağlantısı kontrolü
def check_internet_connection():
    """İnternet bağlantısını kontrol eder."""
    try:
        requests.get("https://www.google.com", timeout=5)
        return True
    except requests.RequestException:
        return False

# Retry decorator - belirli fonksiyonlar için yeniden deneme mekanizması
def retry_on_connection_error(max_retries=10, delay=30):
    """Bağlantı hataları durumunda belirtilen fonksiyonu tekrar dener."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            retries = 0
            while retries <= max_retries:
                try:
                    return func(*args, **kwargs)
                except (requests.RequestException, ConnectionError) as e:
                    wait_time = delay * (retries + 1)
                    retries += 1
                    logger.warning(f"{func.__name__} fonksiyonu başarısız oldu: {e}")
                    logger.info(f"İnternet bağlantısı kontrol ediliyor...")
                    
                    # İnternet bağlantısını bekle
                    while not check_internet_connection():
                        logger.warning(f"İnternet bağlantısı bulunamadı. {wait_time} saniye sonra tekrar denenecek...")
                        time.sleep(wait_time)
                    
                    if retries <= max_retries:
                        logger.info(f"İnternet bağlantısı kuruldu. {func.__name__} fonksiyonu tekrar deneniyor...")
                    else:
                        logger.error(f"Maksimum deneme sayısına ({max_retries}) ulaşıldı. İşlem başarısız.")
            return None
        return wrapper
    return decorator

# Google Drive'dan links.txt dosyasını indirme fonksiyonu
@retry_on_connection_error()
def download_links_from_gdrive(file_id=None):
    """Google Drive'dan links.txt dosyasını indirir veya mevcut dosyayı kontrol eder."""
    output_file = "links.txt"
    
    # Dosyanın var olup olmadığını kontrol et
    if os.path.exists(output_file):
        logger.info("links.txt dosyası zaten mevcut. Tekrar indirilmeyecek.")
    else:
        # Dosya yoksa Drive ID'yi sor veya parametre olarak verileni kullan
        if not file_id:
            file_id = input("Google Drive'daki links.txt dosyasının ID'sini girin: ").strip()
            logger.info("Örnek: https://drive.google.com/file/d/BU_ID_KISMI/view")
        
        logger.info("Google Drive'dan links.txt dosyası indiriliyor...")
        try:
            url = f"https://drive.google.com/uc?id={file_id}"
            gdown.download(url, output_file, quiet=False)
            logger.info(f"links.txt dosyası başarıyla indirildi.")
        except Exception as e:
            logger.error(f"Hata: links.txt dosyası indirilemedi. Sebep: {e}")
            return []
    
    # Dosyanın içeriğini kontrol et ve işaretli olmayan linkleri al
    try:
        with open(output_file, "r", encoding="utf-8") as file:
            links = []
            for line in file:
                line = line.strip()
                if line and not line.endswith("#"):  # İşaretli olmayan linkleri al
                    links.append(line)
            logger.info(f"Toplam {len(links)} işaretlenmemiş link bulundu.")
        return links
    except Exception as e:
        logger.error(f"Hata: links.txt dosyası okunamadı. Sebep: {e}")
        return []

# Linkleri işaretleme fonksiyonu
def mark_link_as_used(link):
    """Kullanılan linki links.txt dosyasında işaretler."""
    try:
        # Dosyayı oku
        with open("links.txt", "r", encoding="utf-8") as file:
            lines = file.readlines()
        
        # İşaretleme yap
        with open("links.txt", "w", encoding="utf-8") as file:
            for line in lines:
                line_stripped = line.strip()
                if line_stripped == link:  # Tam eşleşme kontrolü
                    file.write(f"{line_stripped}#\n")  # İşaretli link
                    logger.info(f"Link işaretlendi: {line_stripped}")
                else:
                    file.write(f"{line_stripped}\n")  # Değiştirilmemiş satır
        
        return True
    except Exception as e:
        logger.error(f"Hata: Link işaretlenemedi. Sebep: {e}")
        return False

# Hashtagleri çekme fonksiyonu
@retry_on_connection_error()
def fetch_hashtags(region):
    """Belirtilen bölgeden hashtagleri # işaretiyle birlikte çeker."""
    url = f"https://trends24.in/{region}/"
    try:
        # Web sayfasından veri çek
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        # Kodlamayı UTF-8 olarak zorla
        response.encoding = 'utf-8'
        
        # BeautifulSoup ile içeriği ayrıştır
        soup = BeautifulSoup(response.text, 'html.parser', from_encoding='utf-8')
        
        # # ile başlayan <a> tag'lerini çek
        hashtags = [item.text.strip() for item in soup.find_all('a', href=True) if item.text.strip().startswith('#')]
        
        # Gereksiz metinleri hariç tutmak için bir liste
        exclude_list = ['home', 'about', 'contact', 'privacy', 'terms', 'login', 'signup']
        
        # Filtrelenmiş hashtag'ler
        filtered_hashtags = []
        for hashtag in hashtags:
            # Türkçe karakterleri normalize et
            normalized_hashtag = unicodedata.normalize('NFC', hashtag)
            # Gereksiz kelimeleri ve çok kısa metinleri filtrele
            if (len(normalized_hashtag) > 2 and 
                normalized_hashtag.lower().lstrip('#') not in exclude_list and
                not normalized_hashtag.lower().startswith(('http', 'www'))):
                filtered_hashtags.append(normalized_hashtag)
        
        logger.info(f"Çekilen tag sayısı: {len(filtered_hashtags)}")
        if filtered_hashtags:
            logger.info(f"İlk birkaç tag: {filtered_hashtags[:5]}")
        return filtered_hashtags
    except requests.RequestException as e:
        logger.error(f"Hata: Tag'ler çekilemedi. Sebep: {e}")
        raise # Retry mekanizması için hataları yukarı ileti

# Rastgele hashtag seçme fonksiyonu
def select_random_hashtags(hashtags, count):
    """Tag'ler arasından rastgele seçim yapar."""
    if not hashtags:
        return []
    count = min(count, len(hashtags))  # İstenen sayı mevcut tag sayısını aşamaz
    selected = random.sample(hashtags, count)
    logger.info(f"Seçilen tag'ler: {selected}")
    return selected

# Grok'tan başlık üretme fonksiyonu 
@retry_on_connection_error()
def generate_title_from_grok(link):
    """Grok AI'ı kullanarak link için bir başlık üretir"""
    logger.info(f"Grok'tan başlık üretiliyor: {link}")
    url = "https://grok.x.com/2/grok/add_response.json"
    
    prompt = f'Aşağıdaki link için X\'te paylaşım için kısa (en az 20 en fazla fazla 150 karakter), ilgi çekici br başlık üret:\n{link}'
    
    payload = {
        "responses": [
            {
                "message": f"Prompt: \"{prompt}\"",
                "sender": 1,
                "promptSource": "",
                "fileAttachments": []
            }
        ],
        "systemPromptName": "",
        "grokModelOptionId": "grok-3",
        "conversationId": "1924161766348493071",
        "returnSearchResults": True,
        "returnCitations": True,
        "promptMetadata": {
            "promptSource": "NATURAL",
            "action": "INPUT"
        },
        "imageGenerationCount": 4,
        "requestFeatures": {
            "eagerTweets": True,
            "serverHistory": True
        },
        "enableSideBySide": False,
        "toolOverrides": {},
        "isDeepsearch": False,
        "isReasoning": False
    }
    
    try:
        response = requests.post(url, data=json.dumps(payload), headers=grok_headers)
        response.raise_for_status()
        
        logger.info(f"Grok yanıt kodu: {response.status_code}")
        
        # Ham yanıtı al
        raw_response = response.text
        
        # Yanıtı satır satır işle
        lines = raw_response.strip().split('\n')
        messages = []
        
        for line in lines:
            try:
                json_obj = json.loads(line)
                if "result" in json_obj and "message" in json_obj["result"]:
                    messages.append(json_obj["result"]["message"])
            except json.JSONDecodeError as e:
                logger.error(f"JSON ayrıştırma hatası: {e}")
        
        # Mesajları birleştir
        baslik = "".join(messages).strip()
        if not baslik:
            baslik = "Sizin için ilgi çekici bir içerik"
            logger.warning("Grok'tan başlık alınamadı, varsayılan başlık kullanılıyor.")
        
        # Grok yanıtındaki yönlendirme metnini temizle
        if ":" in baslik:
            # Genellikle "Başlık:" veya "İşte başlık:" gibi önekleri kaldır
            parts = baslik.split(":", 1)
            if len(parts) > 1:
                baslik = parts[1].strip()
        
        # Tırnak işaretlerini temizle
        baslik = baslik.strip('"\'')
        
        logger.info(f"Üretilen başlık: {baslik}")
        return baslik
    except Exception as e:
        logger.error(f"Başlık üretme hatası: {e}")
        return "İlginç bir içerik keşfedin"

# Tweet gönderme fonksiyonu
@retry_on_connection_error()
def send_tweet(tweet_content, headers, url):
    """Tweet gönderme işlemini gerçekleştirir."""
    payload = {
        "variables": {
            "tweet_text": tweet_content,
            "dark_request": False,
            "media": {
                "media_entities": [],
                "possibly_sensitive": False
            },
            "semantic_annotation_ids": [],
            "disallowed_reply_options": None
        },
        "features": {
            "premium_content_api_read_enabled": False,
            "communities_web_enable_tweet_community_results_fetch": True,
            "c9s_tweet_anatomy_moderator_badge_enabled": True,
            "responsive_web_grok_analyze_button_fetch_trends_enabled": False,
            "responsive_web_grok_analyze_post_followups_enabled": True,
            "responsive_web_jetfuel_frame": False,
            "responsive_web_grok_share_attachment_enabled": True,
            "responsive_web_edit_tweet_api_enabled": True,
            "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
            "view_counts_everywhere_api_enabled": True,
            "longform_notetweets_consumption_enabled": True,
            "responsive_web_twitter_article_tweet_consumption_enabled": True,
            "tweet_awards_web_tipping_enabled": False,
            "responsive_web_grok_show_grok_translated_post": False,
            "responsive_web_grok_analysis_button_from_backend": False,
            "creator_subscriptions_quote_tweet_preview_enabled": False,
            "longform_notetweets_rich_text_read_enabled": True,
            "longform_notetweets_inline_media_enabled": True,
            "profile_label_improvements_pcf_label_in_post_enabled": True,
            "rweb_tipjar_consumption_enabled": True,
            "verified_phone_label_enabled": False,
            "articles_preview_enabled": True,
            "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
            "freedom_of_speech_not_reach_fetch_enabled": True,
            "standardized_nudges_misinfo": True,
            "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
            "responsive_web_grok_image_annotation_enabled": True,
            "responsive_web_graphql_timeline_navigation_enabled": True,
            "responsive_web_enhance_cards_enabled": False
        },
       "queryId": "ff4oWQ3TfCipHY-22RIgKg"
    }

    response = requests.post(url, data=json.dumps(payload), headers=headers)
    response.raise_for_status()  # Hata durumunda exception fırlatır, retry mekanizması için
    logger.info(f"Tweet atıldı: {tweet_content}")
    logger.info(f"Yanıt kodu: {response.status_code}")
    return response.status_code

# Başlık ve linkleri kaydetme fonksiyonu kaldırıldı

# Ana program fonksiyonu
def main():
    logger.info("Hoş geldiniz! Grok + Hashtag + Tweet programı başlatılıyor.")
    
    # Önceki program durumunu yükle
    saved_state = load_state()
    
    if saved_state:
        # Kaydedilmiş durumu kullan
        region = saved_state.get("region")
        hashtag_count = saved_state.get("hashtag_count")
        interval = saved_state.get("interval")
        remaining_links = saved_state.get("remaining_links", [])
        use_grok = saved_state.get("use_grok", True)
        file_id = saved_state.get("file_id", None)
        
        logger.info(f"Önceki durumdan devam ediliyor. {len(remaining_links)} işlenmemiş link bulundu.")
        
        # Kullanıcıya bilgi ver ve onay iste
        print(f"\nÖnceki program durumu yüklendi:")
        print(f"- Bölge: {region}")
        print(f"- Hashtag sayısı: {hashtag_count}")
        print(f"- Zaman aralığı: {interval} saniye")
        print(f"- Grok başlık üretimi: {'Açık' if use_grok else 'Kapalı'}")
        print(f"- Kalan link sayısı: {len(remaining_links)}")
        
        continue_previous = input("\nÖnceki işlemden devam etmek istiyor musunuz? (e/h): ").strip().lower()
        
        if continue_previous != 'e':
            logger.info("Kullanıcı yeni bir başlangıç yapmak istiyor.")
            saved_state = None
    
    if not saved_state:
        # Yeni bir program başlat
        # Bölge bilgisini al
        region = input("Hashtaglerin çekileceği bölgeyi girin (örneğin, turkey, united-states): ").strip().lower()

        # Hashtag sayısını al
        while True:
            try:
                hashtag_count = int(input("Her tweet için kaç hashtag eklensin? (örneğin, 3): "))
                if hashtag_count > 0:
                    break
                logger.warning("Hata: Hashtag sayısı pozitif bir sayı olmalı.")
            except ValueError:
                logger.warning("Hata: Lütfen geçerli bir sayı girin.")

        # Google Drive dosya ID'sini sor
        file_id = input("Google Drive'daki links.txt dosyasının ID'sini girin (Enter'a basarsanız mevcut dosya kullanılacak): ").strip()
        
        # Google Drive'dan linkleri indir veya mevcut dosyayı kontrol et
        links = download_links_from_gdrive(file_id if file_id else None)
        remaining_links = links  # Tüm linkler işlenecek

        # Eğer linkler indirilemezse programı sonlandır
        if not remaining_links:
            logger.error("Program sonlandırılıyor: links.txt dosyası indirilemedi veya boş.")
            return

        # Zaman aralığını kullanıcıdan al
        while True:
            try:
                interval = int(input("Kaç saniyede bir tweet atılsın? "))
                if interval > 0:
                    break
                logger.warning("Hata: Zaman aralığı pozitif bir sayı olmalı.")
            except ValueError:
                logger.warning("Hata: Lütfen geçerli bir sayı girin.")
        
        # Grok başlık üretimi kullanılsın mı?
        use_grok_input = input("Grok ile başlık üretilsin mi? (e/h): ").strip().lower()
        use_grok = use_grok_input == 'e'
        logger.info(f"Grok başlık üretimi: {'Açık' if use_grok else 'Kapalı'}")
        
        # Linkleri rastgele sırala
        random.shuffle(remaining_links)

    # Tweet API URL
    tweet_url = "https://x.com/i/api/graphql/ff4oWQ3TfCipHY-22RIgKg/CreateTweet"
    
    # Başlık ve link dosyası oluşturma kaldırıldı
    logger.info("Program başlık ve linkleri dosyaya kaydetmeyecek, doğrudan tweet içeriğine ekleyecek.")
    
    # Program durumu
    program_state = {
        "region": region,
        "hashtag_count": hashtag_count,
        "interval": interval,
        "remaining_links": remaining_links,
        "use_grok": use_grok,
        "file_id": file_id
    }
    
    # Program durumunu kaydet
    save_state(program_state)
    
    logger.info(f"Program başlatıldı. İşlenecek link sayısı: {len(remaining_links)}")
    
    # Ana döngü - tüm linkler işlenene kadar devam et
    try:
        while remaining_links:
            # İşlenecek bir sonraki linki al
            current_link = remaining_links.pop(0)
            logger.info(f"İşleniyor: {current_link}")
            
            try:
                # Hashtagleri çek
                hashtags = fetch_hashtags(region)
                
                # Rastgele hashtag seç
                selected_hashtags = select_random_hashtags(hashtags, hashtag_count)
                
                # Hashtag metnini oluştur
                hashtag_text = " ".join(selected_hashtags)
                
                # Tweet içeriğini oluştur
                if use_grok:
                    # Grok'tan başlık üret
                    title = generate_title_from_grok(current_link)
                    tweet_content = f"{title}\n\n{current_link}\n\n{hashtag_text}"
                else:
                    # Sadece link ve hashtag'leri kullan
                    tweet_content = f"{current_link}\n\n{hashtag_text}"
                
                # Tweet gönder
                send_tweet(tweet_content, headers, tweet_url)
                
                # Kullanılan linki işaretle
                mark_link_as_used(current_link)
                
                # Her tweet sonrası program durumunu güncelle ve kaydet
                program_state["remaining_links"] = remaining_links
                save_state(program_state)
                
                # Belirtilen süre kadar bekle
                logger.info(f"{interval} saniye bekleniyor...")
                time.sleep(interval)
                
            except Exception as e:
                logger.error(f"Link işlenirken hata oluştu: {e}")
                # Hata durumunda bile program durumunu kaydet
                program_state["remaining_links"] = remaining_links
                save_state(program_state)
                
                # Hata sonrası kısa bir süre bekle ve devam et
                time.sleep(10)
                continue
        
        logger.info("Tüm linkler başarıyla işlendi!")
        
    except KeyboardInterrupt:
        logger.info("Program kullanıcı tarafından durduruldu.")
        # Programı durdururken son durumu kaydet
        program_state["remaining_links"] = remaining_links
        save_state(program_state)
    
    except Exception as e:
        logger.error(f"Beklenmeyen hata: {e}")
        # Beklenmeyen hata durumunda son durumu kaydet
        program_state["remaining_links"] = remaining_links
        save_state(program_state)
    
    finally:
        logger.info("Program sonlandırılıyor.")
        # Kalan link sayısını göster
        if remaining_links:
            logger.info(f"İşlenmemiş {len(remaining_links)} link kaldı.")
        else:
            logger.info("Tüm linkler işlendi.")

# Programı çalıştır
if __name__ == "__main__":
    main()