import json
import urllib.request
import urllib.parse
import time
import os
import threading
import requests
from bs4 import BeautifulSoup

TOKEN = "8249717250:AAG4FRUnhglSLP9FsvNfsxrryMOk42xCtLg"  # Kendi token'ını buraya yaz
URL = f"https://api.telegram.org/bot{TOKEN}/"
DATA_FILE = "takip_edilenler.json"

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
    except Exception as e:
        print(f"Mesaj gönderme hatası: {e}")

def background_price_checker():
    while True:
        time.sleep(7200)
        data = load_data()
        for chat_id, items in data.items():
            updated = False
            for item in items:
                old_price = item['price']
                _, new_price = get_product_info(item['url'])
                if new_price and new_price != "Fiyat okunamadı" and new_price != old_price:
                    item['price'] = new_price
                    updated = True
                    send_message(chat_id, f"🔔 **Fiyat Güncellendi!**\n\n📌 {item['title']}\n💰 Eski: {old_price}\n💰 Yeni: {new_price}")
            if updated: save_data(data)

def get_updates(offset=None):
    url = URL + "getUpdates?timeout=100"
    if offset: url += f"&offset={offset}"
    try:
        response = urllib.request.urlopen(url)
        return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f"Bağlantı/Token Hatası: {e}")  # Artık hatayı ekranda göreceğiz!
        return None

def main():
    threading.Thread(target=background_price_checker, daemon=True).start()
    print("Bot çalışıyor, mesajlar bekleniyor...")
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
                        reply = "Merhaba! Fiyat takip botu aktif. Ürün linki gönderebilirsin."
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
                            reply = f"✅ Eklendi!\n\n📌 {title}\n💰 {price}"
                        else:
                            reply = f"❌ Eklenemedi: {price}"
                    else:
                        reply = "Lütfen geçerli bir link gönderin."
                    
                    send_message(chat_id, reply)
        time.sleep(1)

if __name__ == '__main__':
    main()