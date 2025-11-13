import asyncio
import os
import re
import xml.etree.ElementTree as ET
from urllib.parse import urlparse
from crawl4ai import AsyncWebCrawler
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

from openai import AsyncOpenAI

from dotenv import load_dotenv
import json

BASE_DIR = "scraped_site"

load_dotenv()

client = AsyncOpenAI(api_key=os.getenv("API_KEY"))

TRIP_CATEGORIES = [
    "Mustang_Treks",
    "Everest_Treks",
    "Annapurna_Treks",
    "Manaslu_Treks",
    "Langtang_Treks",
    "Ganesh_Himal_Treks",
    "Peak_Climbing_in_Nepal",
    "Jungle_Safari_in_Nepal"
]

async def classify_trip_page(title: str, content: str):
    prompt = f"""
You are a Nepal travel content classifier.
Categorize the page below into one of the following categories:


{json.dumps(TRIP_CATEGORIES, indent=2)}

Know exclusively that https://www.discoveryworldtrekking.com/trips/island-peak-climbing-with-ebc belongs to Everest_Treks category.

If no clear match, return "Other_Trips".

Title: {title}
Content (first 600 chars): {content[:2000]}

Return only the category name.
"""
    resp = await client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    print(content[:2000])
    return resp.choices[0].message.content.strip()


def url_to_markdown_filename(url: str) -> str:
    """
    Convert a URL into a clean markdown filename.
    """
    parsed = urlparse(url)
    path = parsed.path.strip('/')

    slug = os.path.basename(path) or "index"

    # Remove unwanted characters (sanitize)
    slug = re.sub(r'[^a-zA-Z0-9_-]', '_', slug)

    # Ensure markdown extension
    if not slug.endswith('.md'):
        slug += '.md'

    return slug


def url_to_dir(base_domain: str, url: str) -> str:
    """Convert URL to directory structure preserving hierarchy."""
    parsed = urlparse(url)
    if parsed.netloc != base_domain:
        return None
    path = parsed.path.strip("/")
    if not path:
        return BASE_DIR  # homepage
    dir_path = os.path.join(BASE_DIR, *path.split("/")[:-1])
    return dir_path

# --------------------------
# Save Page
# --------------------------
def save_page(local_dir: str, filename: str, data: str):
    os.makedirs(local_dir, exist_ok=True)
    filepath = os.path.join(local_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(data)
    print(f"✅ Saved: {filepath}")

# -----------------------------
# Utility: Read URLs from sitemap.xml
# -----------------------------
def read_urls_from_sitemap(xml_path: str):
    tree = ET.parse(xml_path)
    root = tree.getroot()
    namespace = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
    urls = [url.find('ns:loc', namespace).text for url in root.findall('ns:url', namespace)]
    return urls


async def crawl_from_sitemap(sitemap_path: str, output_dir: str, start_url: str):
    parsed_start = urlparse(start_url)
    base_domain = parsed_start.netloc
    # Read sitemap URLs
    urls = read_urls_from_sitemap(sitemap_path)
    print(f"🕸️ Found {len(urls)} URLs to crawl.")

    run_config = CrawlerRunConfig(markdown_generator=DefaultMarkdownGenerator())
 
    async with AsyncWebCrawler() as crawler:  
        for url in urls:
            result = await crawler.arun(url=url, config=run_config)

            if re.search(r"/trips/", result.url, re.I):
                path = url_to_dir(base_domain=base_domain, url=result.url)

                if path is None:
                    continue
                
                if len(path.split("/")) > 2:
                    file_name = path.split("/")[-1] + ".md"
                    url = "https://www.discoveryworldtrekking.com/trips/inquiries"
                    path = url_to_dir(base_domain=base_domain, url=url)
                    path = os.path.join(path, "inquiries")
                    save_page(local_dir=path, filename=file_name, data=result.markdown)
                    continue

                category = await classify_trip_page(
                    title=result.metadata.get("title", ""),
                    content=result.markdown
                    )

                file_name = url_to_markdown_filename(result.url)
                path = os.path.join(path, category)

            else:
                path = url_to_dir(base_domain=base_domain, url=result.url)
                file_name = url_to_markdown_filename(result.url)
                
            if path:
                save_page(local_dir=path, filename=file_name, data=result.markdown)


if __name__ == "__main__":
    for link in ["sitemap.xml","unvisited_sitemap.xml"]:
        asyncio.run(crawl_from_sitemap(
            sitemap_path=link,        
            output_dir="scraped_site" ,
            start_url="https://www.discoveryworldtrekking.com"     
        )
        )

