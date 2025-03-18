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
