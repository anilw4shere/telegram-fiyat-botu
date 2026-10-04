import json
import urllib.request
import urllib.parse
import time
import os
import threading
import requests
from bs4 import BeautifulSoup
from http.server import HTTPServer, BaseHTTPRequestHandler

TOKEN = "8249717250:AAG4FRUnhglSLP9FsvNfsxrryMOk42xCtLg"  # Kendi Token'ını buraya yaz
URL = f"https://api.telegram.org/bot{TOKEN}/"
DATA_FILE = "takip_edilenler.json"

class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot aktif ve calisiyor!")

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), SimpleHandler)
    server.serve_forever()

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def get_product_info(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return None, "Siteye erişilemedi."
        
        soup = BeautifulSoup(response.text, 'html.parser')
        title = soup.title.string.strip() if soup.title else "Ürün Adı Bulunamadı"
        
        price_text = None
        if "ikea.com.tr" in url:
            price_elem = soup.find("span", {"id": "price1"}) or soup.find("div", {"class": "product-price"})
            if price_elem: price_text = price_elem.get_text().strip()
        elif "amazon.com.tr" in url:
            price_elem = soup.find("span", {"class": "a-price-whole"})
            if price_elem: price_text = price_elem.get_text().strip() + " TL"
        elif "trendyol.com" in url:
            price_elem = soup.find("span", {"class": "prc-dsc"})
            if price_elem: price_text = price_elem.get_text().strip()
            
        if not price_text:
            price_candidates = soup.find_all(class_=lambda x: x and ('price' in x.lower() or 'fiyat' in x.lower()))
            for candidate in price_candidates:
                text = candidate.get_text().strip()
                if 'TL' in text or '₺' in text or any(char.isdigit() for char in text):
                    price_text = text
                    break
        
        if not price_text: price_text = "Fiyat okunamadı"
        return title[:50], price_text
    except Exception as e:
        return None, f"Hata: {str(e)}"

def send_message(chat_id, text):
    try:
        text_encoded = urllib.parse.quote(text)
        urllib.request.urlopen(f"{URL}sendMessage?chat_id={chat_id}&text={text_encoded}")
    except:
        pass

def background_price_checker():
    while True:
        # 30 dakikada bir kontrol (30 * 60 = 1800 saniye)
        time.sleep(10) 
        data = load_data()
        for chat_id, items in data.items():
            updated = False
            for item in items:
                old_price = item['price']
                _, new_price = get_product_info(item['url'])
                
                if new_price and new_price != "Fiyat okunamadı" and new_price != old_price:
                    # Fiyat değişim yönünü belirleyelim (basitçe karakter uzunluğu veya metin kıyaslaması yerine bilgilendirici başlık)
                    item['price'] = new_price
                    updated = True
                    
                    message = (
                        f"🔔 **Fiyat Değişikliği Alarmı!**\n\n"
                        f"📌 {item['title']}\n"
                        f"🔗 {item['url']}\n\n"
                        f"💰 **Eski Fiyat:** {old_price}\n"
                        f"🏷️ **Yeni Fiyat:** {new_price}"
                    )
                    send_message(chat_id, message)
            if updated: 
                save_data(data)

def get_updates(offset=None):
    url = URL + "getUpdates?timeout=100"
    if offset: url += f"&offset={offset}"
    try:
        response = urllib.request.urlopen(url)
        return json.loads(response.read().decode('utf-8'))
    except:
        return None

def main():
    threading.Thread(target=run_web_server, daemon=True).start()
    threading.Thread(target=background_price_checker, daemon=True).start()
    
    print("30 dakikalık kontrol döngüsüyle Fiyat Avcısı aktif...")
    offset = None
    while True:
        updates = get_updates(offset)
        if updates and "result" in updates:
            for update in updates["result"]:
                offset = update["update_id"] + 1
                if "message" in update and "text" in update["message"]:
                    chat_id = str(update["message"]["chat"]["id"])
                    user_message = update["message"]["text"].strip()
                    
                    data = load_data()
                    if chat_id not in data: data[chat_id] = []
                    
                    msg_lower = user_message.lower()
                    if msg_lower == "/start":
                        reply = "Merhaba! 30 dakikada bir fiyatları tarayan ve değişimleri bildiren bot aktif."
                    elif msg_lower == "/takipteyim":
                        user_list = data[chat_id]
                        reply = "📦 Takip Ettiğin Ürünler:\n\n" + "\n".join([f"{i+1}. {item['title']}\n🔗 {item['url']}\n💰 {item['price']}\n" for i, item in enumerate(user_list)]) if user_list else "Takip ettiğin ürün yok."
                    elif msg_lower == "/temizle":
                        data[chat_id] = []
                        save_data(data)
                        reply = "Liste temizlendi."
                    elif user_message.startswith("http://") or user_message.startswith("https://"):
                        send_message(chat_id, "Ürün taranıyor...")
                        title, price = get_product_info(user_message)
                        if title:
                            data[chat_id].append({"url": user_message, "title": title, "price": price})
                            save_data(data)
                            reply = f"✅ Eklendi ve Alarm Kuruldu!\n\n📌 {title}\n💰 {price}"
                        else:
                            reply = f"❌ Eklenemedi: {price}"
                    else:
                        reply = "Lütfen geçerli bir link gönderin."
                    
                    send_message(chat_id, reply)
        time.sleep(1800)

if __name__ == '__main__':
    main()