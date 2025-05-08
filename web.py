import os
import json
import asyncio
import logging
from datetime import datetime
from typing import Dict, List
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode, BrowserConfig
from crawl4ai.async_crawler_strategy import AsyncPlaywrightCrawlerStrategy
from crawl4ai.browser_manager import BrowserManager
from langchain_ollama import ChatOllama
from crawl4ai.extraction_strategy import JsonCssExtractionStrategy
import re
#todo: add pics schema 
#todo:modify  description schema : sidebar-inner ng-tns-c4084399552-3 .caption not working properly.
#todo: modify URLs
#todo: implement stage management. to create a system that allows pausing at different stages for different brands. stages coule be: extract_links, store_links, update_links, extract_data, store_data

# Patch for browser closure issue
async def patched_async_playwright__crawler_strategy_close(self) -> None:
    """
    Close the browser and clean up resources.

    This patch addresses an issue with Playwright instance cleanup where the static instance
    wasn't being properly reset, leading to issues with multiple crawls.

    Issue: https://github.com/unclecode/crawl4ai/issues/842

    Returns:
        None
    """
    await self.browser_manager.close()

    # Reset the static Playwright instance
    BrowserManager._playwright_instance = None

# Apply the patch
AsyncPlaywrightCrawlerStrategy.close = patched_async_playwright__crawler_strategy_close

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__) #create a logger

# MongoDB Connection
try:
    client = MongoClient("mongodb://192.168.100.150:27017/", serverSelectionTimeoutMS=5000)
    client.server_info()  # Will throw an exception if connection fails
    db = client["competitors"]
    collection = db["dresses"]
    logger.info("Successfully connected to MongoDB")
except ConnectionFailure as e:
    logger.error(f"Failed to connect to MongoDB: {e}")
    raise

# Configuration
PROD_LIMIT = int(os.environ.get('PROD_LIMIT', 5)) #This line sets the PROD_LIMIT variable to the value of the PROD_LIMIT environment variable, or 5 if the variable is not set.
#LLM_MODEL = os.environ.get('LLM_MODEL', "deepseek-r1")
PROXY_USER = os.environ.get('PROXY_USER', 'web_crawler_gOE9S')
PROXY_PASS = os.environ.get('PROXY_PASS', 'Decrease_Subtotal6_Stencil')
PROXY_SERVER = f"http://customer-{PROXY_USER}-cc-us-sessid-0821780918-sesstime-10:{PROXY_PASS}@pr.oxylabs.io:7777"

# List of URLs to crawl
URLs = [
    # "https://www.justinalexander.com/justin-alexander/wedding-dresses/",
    # "https://www.allurebridals.com/dresses/allure-bridals-dresses/",
    # "https://www.essensedesigns.com/martina-liana/wedding-dresses/", 
    # "https://www.essensedesigns.com/wedding-dresses/",
    # "https://www.maggiesottero.com/find-your-style#designers=2"
]

# Schema for wedding dress product pages
WEDDING_DRESS_SCHEMA = {
    "name": "Wedding Dress Product",
    "baseSelector": "body",
    "fields": [
        {
            "name": "name", 
            "selector": "h1",
            "type": "text",
            "cleanup": {"method": "strip"},
            "fallback": {
                "selector": "h1 .header-div, .product-name, .product-title, [itemprop='name']",
                "extract": {
                    "method": "regex",
                    "pattern": r"^(\w+)",
                    "flags": "g"  # Global flag (find all matches, not just the first)
                }
            }
        },
        {
            "name": "description",
            "selector": ".product-description, .product-details, [class*='details'], .details-section, .productDetails, .product-info, .specifications, .sub-heading, .tabs-content, .description-hook",
            "type": "text",
            "required": False,
            "extract": {
                "method": "regex",
                "pattern": r"(?s)(.*?)(?=Silhouette:|$).*?(Silhouette:.*?)(?=Neckline:|$).*?(Neckline:.*?)(?=Waistline:|$).*?(Waistline:.*?)(?=Trend:|$).*?(Trend:.*?)(?=Figure:|$).*?(Figure:.*?)(?=Fabric:|$).*?(Fabric:.*?)(?=Train length:|$).*?(Train length:.*?)$",
                "flags": "s"
            },
        },
        {
            "name": "sidebar",
            "selector": ".caption",
            "type": "text",
            "extract": {
                    "method": "all",
                    "transform": ["trim"]
                    },
            "multiple": True,
            "postprocess": {
                     "method": "join",
                     "separator": ", ",
                     "prefix": "Dress Highlights: ",
                     "transform": ["replace:/\s+/g: "]  # replaces multiple spaces with single space
                    }
        },
        {
            "name": "url",
            "selector": "[rel='canonical'], link[rel='canonical']",
            "type": "attribute",
            "attribute": "href"
        }
    ]
}
# <div class="class="ng-tns-c4084399552-3 sidebar sidebar-right ng-trigger ng-trigger-slider" ">Main Features</div>
# <div class="sidebar-inner ng-tns-c4084399552-3">
# <div class="feature-sidebar ng-tns-c4084399552-3">
# <div class="sidebar-text">
# <section class="highlight-container">
# <h2>
# <div class="grid-container">
# <div class="grid-item highlight ng-star-inserted">
# <image>
# <div _ngcontent-serverapp-c3181953466="" class="caption">Soft tulle</div>
# <div _ngcontent-serverapp-c3181953466="" class="caption">X</div>
# <div _ngcontent-serverapp-c3181953466="" class="caption">YYYY</div>
# <div _ngcontent-serverapp-c3181953466="" class="caption">Soft </div>
# <div _ngcontent-serverapp-c3181953466="" class="caption">tulle</div>

async def extract_pdp_links(url: str) -> List[str]:
    """Extract PDP links using crawl4ai's lazy loading features."""
    logger.info(f"=== Starting PDP Links Extraction for {url} ===")
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Configure crawler for lazy loading with longer delays
            crawler_config = CrawlerRunConfig(
                wait_for_images=True,  # true:Forces full image loading before scraping
                scan_full_page=True,  # true:Scans the entire page, including content that requires scrolling (e.g., lazy-loaded images, infinite scroll sections, with "Load More" buttons)
                scroll_delay=2.0,  # Increased from 0.5 to 2.0 seconds
                cache_mode=CacheMode.ENABLED, #cache_mode=CacheMode.BYPASS - Never reuses cached resources
                verbose=True, #enables detailed logging of the crawling process, useful for debugging and monitoring. 1.Process Tracking 2. Error Visibility 3. Performance Metrics. Example: [TIME] Page load: 1.4s | Extraction: 0.2s
                page_timeout=180000,
                word_count_threshold=1, #Extracts every text element containing at least 1 word
            )

            browser_config = BrowserConfig(
                headless=True, #Use headless=False only when debugging or dealing with bot detection.  it consumes more CPU/RAM and runs slower than headless mode.
                proxy=PROXY_SERVER,
                viewport_width=1920,
                viewport_height=1080,
                ignore_https_errors=True,  # Ignore SSL certificate errors
                # block_resources=["image", "media", "font"]  # this block images and other heavy resources, but it's not supported by crawl4ai
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"  #Mozilla/5.0	Always included	Legacy compatibility. AppleWebKit/537.36	Rendering engine. (KHTML, like Gecko)	Engine compatibility
            )

            crawler = None #This line initializes the crawler variable as None.
            try:
                crawler = AsyncWebCrawler(config=browser_config)
                await crawler.start() #This line starts the crawler.
                result = await crawler.arun(url, config=crawler_config)
                
                if not result.success:
                    logger.error(f"Failed to crawl URL: {url}")
                    if attempt < max_retries - 1:
                        logger.warning(f"Attempt {attempt + 1} failed, retrying...") 
                        await asyncio.sleep(2)  # Wait before retrying
                        continue
                    return []

                # Get the links dictionary directly
                links_dict = result.links 
                if not links_dict:
                    logger.error("No links found in result")
                    return []

                # Log the raw links for debugging
                logger.info(f"Links dictionary structure: {links_dict.keys()}")  #result.links Contains different types of links found on the page.Each key represents a category of links such as internal links, external links, etc.
                
                # Typical keys we might see:
                # {
                #     'internal': [...],      # Links within the same domain
                #     'external': [...],      # Links to other domains
                #     'images': [...],        # Image URLs
                #     'scripts': [...],       # JavaScript files
                #     'stylesheets': [...],   # CSS files
                #     'anchors': [...],       # Anchor tags
                #     'canonical': [...],     # Canonical URLs
                #     'meta': [...]          # Meta tag URLs
                # }


                # Extract all links from the page
                pdp_links = []  #[] is the Python syntax for creating an empty list

                for link_type, links in links_dict.items():  # items() is a dictionary method.Returns: Pairs of (key, value) from the dictionary
                    logger.info(f"Processing {len(links)} links of type: {link_type}")
                    for link in links:
                        # if else here: Check if link is dictionary.If yes: extract 'href' value.If no: convert to string
                        if isinstance(link, dict): # Checks if an object is an instance of a class. here to check if the link is a dictionary. Returns: True if object is instance of class, False otherwise
                            link_url = link.get('href', '') #The get() method is a dictionary method that returns the value for a specified key if the key exists in the dictionary,if not, returns empty string '' here
                        else:
                            link_url = str(link) #Converts the link to a string

                        if not link_url: #empty check. if link_url is empty, skip to the next iteration of the loop. if not, continue processing
                            continue

                        # pattern matching: Check if it's a PDP link based on URL patterns
                        if any([ #Returns True if ANY condition is True
                            # Justin Alexander pattern
                            ('justinalexander.com' in link_url and  #URL contains the domain
                             '/wedding-dresses/' in link_url and  #path segments
                             ('/88415/' in link_url or 'plp_url=' in link_url)),
                            
                            # Allure Bridals pattern
                            ('allurebridals.com' in link_url and 
                             '/dresses/' in link_url and
                             'allure-bridals-dresses' in link_url and
                             not link_url.endswith('/dresses/')),
                            
                            # Martina Liana pattern
                            ('essensedesigns.com' in link_url and
                             '/martina-liana/' in link_url and 
                             '/wedding-dresses/' in link_url and
                             not link_url.endswith('/wedding-dresses/') and
                             (re.search(r'\d{4}\+?$', link_url) is not None)), #\d{4}: Matches exactly 4 digits; \+?: Optional plus sign; $: End of string
                             #re.search(pattern, string). Returns a match object if found; Returns None if not found. Regular string: "\\d{4}"   Raw string: r"\d{4}"  
                            
                            # Maggie Sottero pattern
                            ('maggiesottero.com' in link_url and 
                             '/maggie-sottero/' in link_url and 
                             not link_url.endswith('/maggie-sottero/') and 
                             (re.search(r'\d{5}$', link_url) is not None)), #\d{5}: Matches exactly 5 digits; $: End of string
                        ]):
                            
                            #logger.info(f"Found PDP link: {link_url}")
                            pdp_links.append(link_url)

                # Remove duplicates URLs from pdp_links by converting the list to a set (which only allows unique values) and back to a list.
                pdp_links = list(set(pdp_links))  

                logger.info(f"Found {len(pdp_links)} PDP links")
                
                # Store PDP links in MongoDB
                for link in pdp_links:
                    try:
                        # Create document with link and timestamp
                        pdp_document = {
                            "url": link, #the pdp link
                            "found_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), #the date and time the link was found
                            "status": "pending"  # pending, completed, failed
                        }
                        
                        # Check if link already exists
                        existing = collection.find_one({"url": link}) #find_one() is a MongoDB method that returns a single document that matches the specified query criteria. syntax: collection.find_one(query, projection)
                        if existing:
                            # Update existing document
                            collection.update_one( #collection.update_one(filter, update, upsert). filter: Criteria to find the document; update: Modifications to apply; upsert: Create if document doesn't exist
                                {"url": link},
                                {
                                    "$set": pdp_document, #$set Behavior: Updates existing fields; Adds new fields; Doesn't remove unspecified fields. here add found_date and status to the exsiting url
                                    "$setOnInsert": {"first_found": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}  #Behavior:Only applies during insert; Ignored during update. here insert first_found date
                                },
                                upsert=True #Behavior:True: Create document if it doesn't exist; False: Only update existing documents
                            )
                            logger.info(f"Updated existing PDP link in MongoDB: {link}")
                        else:
                            # Add first_found date for new documents
                            pdp_document["first_found"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            collection.insert_one(pdp_document)
                            logger.info(f"Inserted new PDP link to MongoDB: {link}")
                            
                    except Exception as e:
                        logger.error(f"Error storing PDP link in MongoDB: {link} - Error: {e}")
                        continue
                
                # Log first few links for verification
                for i, link in enumerate(pdp_links[:3]):
                    logger.info(f"PDP Link {i+1}: {link}")
                
                return pdp_links
            finally:
                if crawler:
                    await crawler.close()

        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"Attempt {attempt + 1} failed with error: {e}, retrying...")
                await asyncio.sleep(2)  # Wait before retrying
                continue
            logger.error(f"Error extracting PDP links after {max_retries} attempts: {e}", exc_info=True)
            return []

# Add stage management
class StageManager:
    def __init__(self):
        self.current_stage = None
        self.stages = {
            "extract_links": "Extracting PDP links from websites",
            "extract_data": "Extracting data from PDP links in MongoDB",
            "store_data": "Storing extracted data in MongoDB"
        }
    
    def set_stage(self, stage_name):
        if stage_name not in self.stages:
            raise ValueError(f"Invalid stage: {stage_name}")
        self.current_stage = stage_name
        logger.info(f"=== Entering stage: {self.stages[stage_name]} ===")
    
    def get_current_stage(self):
        return self.current_stage

# Initialize stage manager
stage_manager = StageManager()

async def extract_and_store_data():
    """Main function to extract data from existing PDP links in MongoDB."""
    logger.info("Starting data extraction process from MongoDB")

    try:
        # # Stage 1: Extract PDP links (optional, can be skipped)
        # stage_manager.set_stage("extract_links")
        # for url in URLs:
        #     logger.info(f"Processing PLP URL: {url}")
        #     await extract_pdp_links(url)
        #     # Add pause point after each URL
        #     logger.info("Press Enter to continue to next URL (or type 'exit' to stop):")
        #     user_input = input()
        #     if user_input.lower() == 'exit':
        #         logger.info("Exiting at user request")
        #         exit()

        # # Stage 2: Extract data from stored PDP links
        # stage_manager.set_stage("extract_data")
        # pending_links = collection.find({"status": "pending"})
        # total_links = collection.count_documents({"status": "pending"})
        # logger.info(f"Found {total_links} pending PDP links to process")
        
        
        
        # Stage 1: Extract data from stored PDP links
        stage_manager.set_stage("extract_data")
        
        # Get all pending links from MongoDB
        pending_links = collection.find({
            "status": "completed",
            "brand": "Maggie Sottero" })
        total_links = collection.count_documents({"status": "completed", "brand": "Maggie Sottero"})
        logger.info(f"Found {total_links} pending Justin Alexander PDP links to process")


        browser_config = BrowserConfig(
            headless=True,
            proxy=PROXY_SERVER,
            viewport_width=1920,
            viewport_height=1080,
            ignore_https_errors=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        )

        crawler_config = CrawlerRunConfig(
            wait_for_images=True,  # Ensure images are loaded for maggie
            scan_full_page=True,  # Scan the entire page for maggie
            scroll_delay=5.0,  # Increased delay for better content loading 3.0~5.0
            cache_mode=CacheMode.ENABLED,
            verbose=True,
            page_timeout=300000,
            word_count_threshold=1,
            extraction_strategy=JsonCssExtractionStrategy(WEDDING_DRESS_SCHEMA)
        )

        # processed_count = 0  # Commented out for now - will be used for progress tracking in future
        async with AsyncWebCrawler(config=browser_config) as main_crawler:
            for link in pending_links:
                url = link["url"]
                # logger.info(f"Processing PDP URL: {url} ({processed_count + 1}/{total_links})")  # Commented out progress tracking
                logger.info(f"Processing PDP URL: {url}")
                
                try:
                    result = await main_crawler.arun(url=url, config=crawler_config)
                    
                    if not result or not result.success:
                        logger.error(f"Failed to crawl PDP URL: {url}")
                        logger.info(f"failed result: {result}")
                        # Mark as failed
                        collection.update_one(
                            {"url": url},
                            {
                                "$set": {#When a link fails,only update: status: Set to "failed" , crawl_date: Current timestamp
                                    "status": "failed",
                                    "crawl_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                }
                            }
                        )
                        continue

                    # Stage 3: Store data
                    stage_manager.set_stage("store_data")
                    if hasattr(result, 'extracted_content') and result.extracted_content:
                        try:
                            extracted_data = json.loads(result.extracted_content)
                            
                            if isinstance(extracted_data, list) and len(extracted_data) > 0:
                                product_data = extracted_data[0]
                                
                                # Determine brand based on URL
                                brand = ""
                                if "justinalexander.com" in url:
                                    brand = "Justin Alexander"
                                elif "allurebridals.com" in url:
                                    brand = "Allure Bridals"
                                elif "essensedesigns.com" in url:
                                    brand = "Martina Liana"
                                elif "maggiesottero.com" in url:
                                    brand = "Maggie Sottero"

                                # Get existing document to preserve found_date and first_found
                                existing = collection.find_one({"url": url})
                                if not existing:
                                    logger.error(f"No existing document found for URL: {url}")
                                    continue

                                # Update existing document with new data
                                update_data = {
                                    "url": url,
                                    "brand": brand,
                                    "name": product_data.get("name", ""),
                                    "description": product_data.get("description", ""),
                                    "sidebar":product_data.get("sidebar", ""),
                                    "status": "completed",
                                    "crawl_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                }

                                # Update document while preserving found_date and first_found
                                collection.update_one(
                                    {"url": url},
                                    {
                                        "$set": update_data,
                                        "$setOnInsert": { #Preserved Fields
                                            "found_date": existing.get("found_date"),
                                            "first_found": existing.get("first_found")
                                        }
                                    }
                                )
                                logger.info(f"Updated product data for URL: {url}")
                            else:
                                logger.error("No product data found in extracted content")
                                # Mark as failed
                                collection.update_one(
                                    {"url": url},
                                    {
                                        "$set": {
                                            "status": "failed",
                                            "crawl_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                        }
                                    }
                                )
                        except json.JSONDecodeError as e:
                            logger.error(f"Failed to parse extracted content as JSON: {e}")
                            # Mark as failed
                            collection.update_one(
                                {"url": url},
                                {
                                    "$set": {
                                        "status": "failed",
                                        "crawl_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                    }
                                }
                            )
                    else:
                        logger.error(f"No content available for PDP URL: {url}")
                        # Mark as failed
                        collection.update_one(
                            {"url": url},
                            {
                                "$set": {
                                    "status": "failed",
                                    "crawl_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                }
                            }
                        )

                except Exception as e:
                    logger.error(f"Error processing PDP {url}: {e}")
                    # Mark as failed
                    collection.update_one(
                        {"url": url},
                        {
                            "$set": {
                                "status": "failed",
                                "crawl_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            }
                        }
                    )
                    continue

    except Exception as e:
        logger.error(f"Error in main process: {e}")
        raise

if __name__ == "__main__":
    try:
        asyncio.run(extract_and_store_data())
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        client.close()
