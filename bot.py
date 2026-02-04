import os
import json
import requests
import asyncio
import aiohttp
import random
import time
from datetime import datetime, timedelta
from telegram import Bot, InputMediaPhoto
from telegram.error import TelegramError
import logging
from bs4 import BeautifulSoup
import re

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
BOT_TOKEN = os.getenv('BOT_TOKEN')
CHANNEL_ID = os.getenv('CHANNEL_ID', '@smartdealsindia5')
AFFILIATE_TAG = os.getenv('AFFILIATE_TAG', 'smartdeals063-21')
AMAZON_COUNTRY = 'IN'  # India
POSTS_PER_HOUR = 5
CHECK_INTERVAL = 3600  # 1 hour in seconds

# Categories to search for deals
CATEGORIES = [
    'electronics',
    'mobiles',
    'laptops',
    'home-kitchen',
    'fashion',
    'beauty',
    'books',
    'toys',
    'sports',
    'grocery'
]

# Emojis for different categories
CATEGORY_EMOJIS = {
    'electronics': '📱💻🔌',
    'mobiles': '📱📞',
    'laptops': '💻🖥️',
    'home-kitchen': '🏠🍳',
    'fashion': '👗👔👠',
    'beauty': '💄💅✨',
    'books': '📚📖',
    'toys': '🎮🧸🎯',
    'sports': '⚽🏸🏃‍♂️',
    'grocery': '🛒🍎🥦'
}

class AmazonDealsBot:
    def __init__(self):
        self.bot = Bot(token=BOT_TOKEN)
        self.session = None
        self.posted_deals = set()
        self.load_posted_deals()
        
    def load_posted_deals(self):
        """Load previously posted deals from file"""
        try:
            with open('posted_deals.json', 'r') as f:
                self.posted_deals = set(json.load(f))
        except FileNotFoundError:
            self.posted_deals = set()
    
    def save_posted_deals(self):
        """Save posted deals to file"""
        with open('posted_deals.json', 'w') as f:
            json.dump(list(self.posted_deals), f)
    
    async def create_session(self):
        """Create aiohttp session"""
        self.session = aiohttp.ClientSession(headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
        })
    
    async def close_session(self):
        """Close aiohttp session"""
        if self.session:
            await self.session.close()
    
    def generate_affiliate_link(self, asin):
        """Generate Amazon affiliate link with tracking"""
        return f"https://www.amazon.in/dp/{asin}/?tag={AFFILIATE_TAG}"
    
    async def search_amazon_deals(self, category, max_pages=3):
        """Search for deals on Amazon"""
        deals = []
        
        for page in range(1, max_pages + 1):
            url = f"https://www.amazon.in/s?k={category}+deals&i=electronics&rh=n%3A976419031%2Cp_n_deal_type%3A26941246031&dc&page={page}"
            
            try:
                async with self.session.get(url) as response:
                    if response.status == 200:
                        html = await response.text()
                        deals.extend(await self.parse_deals_page(html))
                    await asyncio.sleep(2)  # Rate limiting
            except Exception as e:
                logger.error(f"Error searching {category}: {e}")
                continue
        
        return deals
    
    async def parse_deals_page(self, html):
        """Parse HTML page for deals"""
        deals = []
        soup = BeautifulSoup(html, 'html.parser')
        
        # Find all product items
        items = soup.find_all('div', {'data-component-type': 's-search-result'})
        
        for item in items:
            try:
                # Extract ASIN
                asin = item.get('data-asin')
                if not asin or asin in self.posted_deals:
                    continue
                
                # Extract title
                title_elem = item.find('h2')
                title = title_elem.text.strip() if title_elem else ""
                
                # Extract price
                price_whole = item.find('span', {'class': 'a-price-whole'})
                price_fraction = item.find('span', {'class': 'a-price-fraction'})
                
                if price_whole:
                    price = price_whole.text.strip()
                    if price_fraction:
                        price += price_fraction.text.strip()
                    price = f"₹{price}"
                else:
                    continue
                
                # Extract original price for discount calculation
                original_price_elem = item.find('span', {'class': 'a-price a-text-price'})
                original_price = ""
                if original_price_elem:
                    original_price_text = original_price_elem.find('span', {'class': 'a-offscreen'})
                    if original_price_text:
                        original_price = original_price_text.text.strip()
                
                # Extract discount
                discount_elem = item.find('span', {'class': 'a-letter-space'})
                discount = ""
                if discount_elem:
                    discount = discount_elem.find_next('span').text.strip() if discount_elem.find_next('span') else ""
                
                # Extract image URL
                img_elem = item.find('img', {'class': 's-image'})
                image_url = img_elem.get('src') if img_elem else ""
                
                # Extract rating
                rating_elem = item.find('span', {'class': 'a-icon-alt'})
                rating = rating_elem.text.strip() if rating_elem else "No rating"
                
                # Extract number of ratings
                ratings_count_elem = item.find('span', {'class': 'a-size-base s-underline-text'})
                ratings_count = ratings_count_elem.text.strip() if ratings_count_elem else "0"
                
                # Generate affiliate link
                affiliate_link = self.generate_affiliate_link(asin)
                
                # Calculate discount percentage if possible
                discount_percentage = ""
                if original_price and price:
                    try:
                        original_num = float(re.sub(r'[^\d.]', '', original_price.replace('₹', '').replace(',', '')))
                        current_num = float(re.sub(r'[^\d.]', '', price.replace('₹', '').replace(',', '')))
                        if original_num > current_num:
                            discount_pct = int(((original_num - current_num) / original_num) * 100)
                            discount_percentage = f"{discount_pct}% OFF"
                    except:
                        pass
                
                deal = {
                    'asin': asin,
                    'title': title,
                    'price': price,
                    'original_price': original_price,
                    'discount': discount,
                    'discount_percentage': discount_percentage,
                    'image_url': image_url,
                    'rating': rating,
                    'ratings_count': ratings_count,
                    'affiliate_link': affiliate_link,
                    'timestamp': datetime.now().isoformat()
                }
                
                # Only add if it has a good discount (optional filter)
                if discount_percentage or "off" in discount.lower() or "%" in discount.lower():
                    deals.append(deal)
                    
            except Exception as e:
                logger.error(f"Error parsing item: {e}")
                continue
        
        return deals
    
    async def get_product_details(self, asin):
        """Get detailed product information"""
        url = f"https://www.amazon.in/dp/{asin}"
        
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Extract detailed description
                    description = ""
                    desc_elem = soup.find('div', {'id': 'productDescription'})
                    if desc_elem:
                        description = desc_elem.get_text(strip=True, separator=' ')
                    
                    # Extract features/bullet points
                    features = []
                    feature_elem = soup.find('div', {'id': 'feature-bullets'})
                    if feature_elem:
                        for li in feature_elem.find_all('li'):
                            features.append(li.get_text(strip=True))
                    
                    return {
                        'description': description[:500] + "..." if len(description) > 500 else description,
                        'features': features[:5]  # Take only first 5 features
                    }
        except Exception as e:
            logger.error(f"Error getting product details for {asin}: {e}")
        
        return {'description': '', 'features': []}
    
    def format_deal_message(self, deal, category):
        """Format deal into a beautiful Telegram message"""
        emoji = CATEGORY_EMOJIS.get(category, '🔥')
        
        # Build message
        message = f"{emoji} *{deal['title']}* {emoji}\n\n"
        
        # Price section
        message += "💰 *PRICE:*\n"
        message += f"➤ Current Price: `{deal['price']}`\n"
        if deal['original_price']:
            message += f"➤ Original Price: ~~{deal['original_price']}~~\n"
        
        # Discount section
        if deal['discount_percentage']:
            message += f"➤ Discount: 🎉 *{deal['discount_percentage']}* 🎉\n"
        elif deal['discount']:
            message += f"➤ Discount: 🎉 {deal['discount']} 🎉\n"
        
        # Rating section
        message += f"\n⭐ *Rating:* {deal['rating']}\n"
        message += f"👥 *Ratings Count:* {deal['ratings_count']}\n"
        
        # Features if available
        if deal.get('features'):
            message += "\n📋 *Key Features:*\n"
            for feature in deal['features']:
                message += f"✓ {feature}\n"
        
        # Description if available
        if deal.get('description'):
            message += f"\n📝 *Description:*\n{deal['description']}\n"
        
        # Link
        message += f"\n🔗 *Direct Link:* [Click Here to Buy]({deal['affiliate_link']})\n"
        
        # Footer
        message += f"\n🕒 Posted: {datetime.now().strftime('%d %b %Y, %I:%M %p')}\n"
        message += f"🏷️ Affiliate Link • #AmazonDeals"
        
        return message
    
    async def download_image(self, image_url):
        """Download image from URL"""
        try:
            async with self.session.get(image_url) as response:
                if response.status == 200:
                    return await response.read()
        except Exception as e:
            logger.error(f"Error downloading image: {e}")
        return None
    
    async def post_to_telegram(self, deal, category):
        """Post deal to Telegram channel"""
        try:
            # Format message
            message = self.format_deal_message(deal, category)
            
            # Download image
            image_data = await self.download_image(deal['image_url'])
            
            if image_data:
                # Send photo with caption
                await self.bot.send_photo(
                    chat_id=CHANNEL_ID,
                    photo=image_data,
                    caption=message,
                    parse_mode='Markdown'
                )
            else:
                # Send text message if image fails
                await self.bot.send_message(
                    chat_id=CHANNEL_ID,
                    text=message,
                    parse_mode='Markdown',
                    disable_web_page_preview=False
                )
            
            # Mark as posted
            self.posted_deals.add(deal['asin'])
            self.save_posted_deals()
            
            logger.info(f"Posted deal: {deal['title'][:50]}...")
            return True
            
        except Exception as e:
            logger.error(f"Error posting to Telegram: {e}")
            return False
    
    async def find_and_post_deals(self):
        """Main function to find and post deals"""
        logger.info("Starting deal search...")
        
        all_deals = []
        
        # Search deals from multiple categories
        for category in CATEGORIES:
            try:
                logger.info(f"Searching {category} deals...")
                deals = await self.search_amazon_deals(category)
                all_deals.extend(deals)
                
                # Get more details for each deal
                for deal in deals:
                    details = await self.get_product_details(deal['asin'])
                    deal.update(details)
                
                await asyncio.sleep(3)  # Rate limiting between categories
                
            except Exception as e:
                logger.error(f"Error processing category {category}: {e}")
                continue
        
        # Sort deals by discount (if available) or rating
        all_deals.sort(key=lambda x: (
            float(x['discount_percentage'].replace('% OFF', '')) 
            if x.get('discount_percentage') and '%' in x['discount_percentage'] 
            else 0
        ), reverse=True)
        
        # Post top deals
        posted_count = 0
        for deal in all_deals:
            if posted_count >= POSTS_PER_HOUR:
                break
            
            if deal['asin'] not in self.posted_deals:
                # Determine category from title
                category = 'electronics'  # Default
                for cat in CATEGORIES:
                    if cat in deal['title'].lower():
                        category = cat
                        break
                
                success = await self.post_to_telegram(deal, category)
                if success:
                    posted_count += 1
                    await asyncio.sleep(10)  # Delay between posts
        
        logger.info(f"Posted {posted_count} deals")
        return posted_count
    
    async def run_continuously(self):
        """Run bot continuously"""
        await self.create_session()
        
        logger.info("Amazon Deals Bot started!")
        logger.info(f"Channel: {CHANNEL_ID}")
        logger.info(f"Affiliate Tag: {AFFILIATE_TAG}")
        
        while True:
            try:
                posted = await self.find_and_post_deals()
                
                if posted == 0:
                    logger.info("No new deals found. Will try again in next cycle.")
                
                # Wait for next cycle
                logger.info(f"Waiting {CHECK_INTERVAL//60} minutes for next cycle...")
                await asyncio.sleep(CHECK_INTERVAL)
                
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                await asyncio.sleep(300)  # Wait 5 minutes on error
    
    async def cleanup(self):
        """Cleanup resources"""
        await self.close_session()

async def main():
    bot = AmazonDealsBot()
    try:
        await bot.run_continuously()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    finally:
        await bot.cleanup()

if __name__ == "__main__":
    asyncio.run(main())