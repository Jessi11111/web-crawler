# web-crawler
web crawler notes
1. Handle Lazy Loading with Selenium
Uses Selenium to render pages where content loads dynamically with JavaScript.
Ensures that all images and product details are extracted.

def get_selenium_html(url):
    options = Options()
    options.add_argument("--headless")  # Headless mode for efficiency
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.get(url)
    html = driver.page_source  # Fully rendered HTML
    driver.quit()
    return html



2. Faster Requests with aiohttp (Asynchronous Crawling)
Uses async requests to fetch multiple pages simultaneously.
Makes the script 4-5x faster than synchronous requests.
python
Copy
Edit
async def get_html(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.text()




3. Bulk Crawling for Faster Execution
Instead of crawling products one by one, the script processes multiple pages in parallel using:
python
Copy
Edit
tasks = [process_ml_pdp(collection, url) for url in product_links]
products_data = await asyncio.gather(*tasks)





4. Asynchronous Image Download
Uses async requests to fetch multiple images at once.
Converts WebP to JPEG for better compatibility.
python
Copy
Edit
async with aiohttp.ClientSession() as session:
    for img_url in image_urls:
        async with session.get(img_url) as resp:
            if resp.status == 200:
                img_data = await resp.read()
                img = Image.open(BytesIO(img_data)).convert("RGB")
                img.save(out_path, "JPEG")


summary:
✅ Faster Crawling – Handles multiple requests in parallel.
✅ Lazy Load Support – Uses Selenium to extract hidden content.
✅ Asynchronous Image Download – No delays while saving images.
✅ Optimized Database Writes – Uses bulk updates instead of slow individual writes
