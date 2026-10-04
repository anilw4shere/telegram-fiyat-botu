import json
import time
import os
import threading
import requests
from bs4 import BeautifulSoup
from http.server import HTTPServer, BaseHTTPRequestHandler

TOKEN = "8249717250:AAG4FRUnhglSLP9FsvNfsxrryMOk42xCtLg"  # Kendi Token'ını buraya yaz
URL = f"https://api.telegram.org/bot{TOKEN}/"
DATA_FILE = "takip_edilenler.json"

# Render'ın 7/24 ayakta tutması için mini web sunucusu
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot aktif!")
    def log_message(self, format, *args):
        return

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), SimpleHandler)
    server.serve_forever()

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    return {}
                return json.loads(content)
        except:
            return {}
    return {}

def save_data(data):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except:
        pass

def send_message(chat_id, text, reply_markup=None):
    try:
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }
        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup)
        requests.post(f"{URL}sendMessage", json=payload, timeout=10)
    except:
        pass

def send_photo_card(chat_id, caption, photo_url, product_url, item_index):
    try:
        reply_markup = {
            "inline_keyboard": [
                [
                    {"text": "🔗 Ürüne Git", "url": product_url},
                    {"text": "❌ Bu Ürünü Sil", "callback_data": f"del_{item_index}"}
                ]
            ]
        }
        payload = {
            "chat_id": chat_id,
            "caption": caption,
            "parse_mode": "Markdown",
            "reply_markup": json.dumps(reply_markup)
        }
        if photo_url:
            payload["photo"] = photo_url
            requests.post(f"{URL}sendPhoto", json=payload, timeout=10)
        else:
            payload["text"] = caption
            requests.post(f"{URL}sendMessage", json=payload, timeout=10)
    except:
        pass

def delete_message(chat_id, message_id):
    try:
        requests.post(f"{URL}deleteMessage", json={"chat_id": chat_id, "message_id": message_id}, timeout=5)
    except:
        pass

def get_product_info(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return None, "Siteye erişilemedi.", None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        title = soup.title.string.strip() if soup.title else "Ürün Adı Bulunamadı"
        
        image_url = None
        og_image = soup.find("meta", property="og:image")
        if og_image and og_image.get("content"):
            image_url = og_image["content"]
        
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
        return title[:50], price_text, image_url
    except Exception as e:
        return None, f"Hata: {str(e)}", None

def show_main_menu(chat_id, text):
    keyboard = {
        "keyboard": [
            [{"text": "📦 Takip Ettiklerim"}],
            [{"text": "🏠 Ana Menü"}, {"text": "🧹 Listeyi Temizle"}]
        ],
        "resize_keyboard": True,
        "is_persistent": True
    }
    send_message(chat_id, text, reply_markup=keyboard)

def background_price_checker():
    while True:
        time.sleep(1800)
        data = load_data()
        for chat_id, items in data.items():
            updated = False
            for item in items:
                old_price = item['price']
                _, new_price, image_url = get_product_info(item['url'])
                if image_url:
                    item['image'] = image_url

                if new_price and new_price != "Fiyat okunamadı" and new_price != old_price:
                    status_icon = "📉 **Fiyat Düştü!**" if new_price < old_price else "📈 **Fiyat Arttı!**"
                    item['price'] = new_price
                    updated = True
                    
                    message = (
                        f"{status_icon}\n\n"
                        f"📌 *{item['title']}*\n\n"
                        f"💰 **Eski Fiyat:** {old_price}\n"
                        f"🏷️ **Yeni Fiyat:** {new_price}"
                    )
                    send_photo_card(chat_id, message, item.get('image'), item['url'], 0)
            if updated: 
                save_data(data)

def main():
    threading.Thread(target=run_web_server, daemon=True).start()
    threading.Thread(target=background_price_checker, daemon=True).start()
    
    print("Bot stabil modda baslatildi...")
    offset = None
    
    while True:
        try:
            params = {"timeout": 30}
            if offset:
                params["offset"] = offset
                
            response = requests.get(f"{URL}getUpdates", params=params, timeout=35)
            res_json = response.json()
            
            if res_json.get("ok") and "result" in res_json:
                for update in res_json["result"]:
                    offset = update["update_id"] + 1
                    
                    if "callback_query" in update:
                        query = update["callback_query"]
                        callback_data = query["data"]
                        chat_id = str(query["message"]["chat"]["id"])
                        message_id = query["message"]["message_id"]
                        
                        if callback_data.startswith("del_"):
                            try:
                                idx = int(callback_data.split("_")[1])
                                data = load_data()
                                if chat_id in data and 0 <= idx < len(data[chat_id]):
                                    removed_item = data[chat_id].pop(idx)
                                    save_data(data)
                                    delete_message(chat_id, message_id)
                                    requests.post(f"{URL}answerCallbackQuery", json={"callback_query_id": query["id"], "text": f"'{removed_item['title'][:15]}...' silindi!"})
                            except:
                                pass

                    elif "message" in update and "text" in update["message"]:
                        chat_id = str(update["message"]["chat"]["id"])
                        message_id = update["message"]["message_id"]
                        user_message = update["message"]["text"].strip()
                        
                        data = load_data()
                        if chat_id not in data: data[chat_id] = []
                        
                        msg_lower = user_message.lower()
                        if msg_lower == "/start" or msg_lower == "merhaba" or user_message == "🏠 Ana Menü" or msg_lower == "/anamenu":
                            show_main_menu(chat_id, "Hoşgeldiniz. Eklemek istediğiniz ürünün linkini gönderiniz.")
                        elif user_message == "📦 Takip Ettiklerim" or msg_lower == "/takipteyim":
                            user_list = data[chat_id]
                            if not user_list:
                                show_main_menu(chat_id, "📭 Takip ettiğin ürün bulunmuyor.")
                            else:
                                show_main_menu(chat_id, f"📦 *Takip Ettiğin Ürünler ({len(user_list)} adet):*")
                                for i, item in enumerate(user_list):
                                    text = f"*{i+1}. Ürün*\n📌 *{item['title']}*\n💰 *Fiyat:* {item['price']}"
                                    send_photo_card(chat_id, text, item.get('image'), item['url'], i)
                        elif user_message == "🧹 Listeyi Temizle" or msg_lower == "/temizle":
                            data[chat_id] = []
                            save_data(data)
                            show_main_menu(chat_id, "🗑️ Tüm liste temizlendi.")
                        elif user_message.startswith("http://") or user_message.startswith("https://"):
                            delete_message(chat_id, message_id)
                            title, price, image_url = get_product_info(user_message)
                            if title:
                                data[chat_id].append({"url": user_message, "title": title, "price": price, "image": image_url})
                                save_data(data)
                                show_main_menu(chat_id, f"✅ *Eklendi:* _{title[:30]}_ ({price})")
                            else:
                                show_main_menu(chat_id, f"❌ Eklenemedi: {price}")
        except Exception as e:
            time.sleep(3)
            
        time.sleep(0.5)

if __name__ == '__main__':
    main()