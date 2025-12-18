import os
from dataclasses import dataclass
from enum import Enum
import email.utils

from datetime import datetime, UTC
from pathlib import Path
from typing import TypedDict
from xml.etree import ElementTree

import boto3
import requests

from config import parse_config, Config


class SitemapUrl(TypedDict):
    url: str
    last_modified: datetime


@dataclass
class PageEntry:
    config_key: str
    api_endpoint: str


class PageAPI(PageEntry, Enum):
    TOPIC = "topics_pages", "2/topics"
    DATASET = "datasets_pages", "2/datasets"
    DATASERVICE = "dataservices_pages", "1/dataservices"


def parse_http_date_with_tz(http_date_str: str) -> datetime:
    dt = email.utils.parsedate_to_datetime(http_date_str)
    return dt.replace(tzinfo=UTC)


def iter_pages(first_url: str, params: dict = {}):
    """
    Iterate through paginated API results.
    """
    url = first_url
    while url:
        r = requests.get(url, params=params)
        r.raise_for_status()
        data = r.json()

        yield from data["data"]
        url = data["next_page"]


def fetch_urls_for_page(page_api: PageAPI, config: Config) -> list[SitemapUrl]:
    results = []
    for page in (getattr(config.website.seo.sitemap_xml, page_api.config_key) or []):
        print(f"-> {page_api.config_key}: {page!r}")
        query = config.pages[page].universe_query
        for remote_object in iter_pages(f"{config.datagouvfr.base_url}/api/{page_api.api_endpoint}/", params=query):
            results.append({
                "url": f"{config.website.seo.canonical_url}/{page}/{remote_object['slug']}",
                "last_modified": datetime.fromisoformat(remote_object["last_modified"]),
            })
    return results


def fetch_urls(config: Config) -> list[SitemapUrl]:
    if not config.website.seo.sitemap_xml:
        print("-> no sitemap.xml config, skipping")
        return []

    results: list[SitemapUrl] = []


    # handle topics
    results += fetch_urls_for_page(PageAPI.TOPIC, config)

    # handle datasets
    results += fetch_urls_for_page(PageAPI.DATASET, config)

    # handle dataservices
    results += fetch_urls_for_page(PageAPI.DATASERVICE, config)

    # handle static pages
    # 1. homepage
    static_urls = ["/"]
    # 2. static pages
    static_urls += [p.route for p in config.website.router.static_pages or []]
    # 3. objects list pages
    for page_api in PageAPI:
        pages = getattr(config.website.seo.sitemap_xml, page_api.config_key) or []
        static_urls += [f"/{p}" for p in pages]
    for relative_url in static_urls:
        abs_url = f"{config.website.seo.canonical_url}{relative_url}"
        r = requests.get(abs_url)
        r.raise_for_status()
        results.append({
            "url": abs_url,
            "last_modified": parse_http_date_with_tz(
                r.headers['last-modified']
            ),
        })

    return results


def create_sitemap(urls: list[SitemapUrl], site_env_path: str) -> str | None:
    """Creates a sitemap XML from a list of URLs."""
    sitemap = ElementTree.Element("urlset", {
        "xmlns": "http://www.sitemaps.org/schemas/sitemap/0.9"
    })

    for url_data in urls:
        url_element = ElementTree.SubElement(sitemap, "url")
        loc = ElementTree.SubElement(url_element, "loc")
        loc.text = url_data["url"]
        lastmod = ElementTree.SubElement(url_element, "lastmod")
        lastmod.text = url_data["last_modified"].isoformat()

    tree = ElementTree.ElementTree(sitemap)
    ElementTree.indent(tree)
    Path(f"dist/{site_env_path}").mkdir(parents=True, exist_ok=True)
    tree.write(f"dist/{site_env_path}/sitemap.xml")


def create_robots(config: Config, site_env_path: str, has_sitemap: bool = True):
    """Creates a robots.txt file."""
    content = "User-agent: *\n"

    if config.website.seo.robots_txt:
        disallow_lines = [f"Disallow: {path}" for path in config.website.seo.robots_txt.disallow or []]
        content += '\n'.join(disallow_lines)

    if has_sitemap:
        content += f"\nSitemap: {config.website.seo.canonical_url}/sitemap.xml"

    site_env_dir = Path(f"dist/{site_env_path}")
    site_env_dir.mkdir(parents=True, exist_ok=True)

    robots_file = site_env_dir / "robots.txt"
    robots_file.write_text(content)


def send_to_s3(site_env_path: str):
    s3_endpoint = os.getenv("AWS_ENDPOINT_URL")
    if not s3_endpoint:
        print("-> S3 not configured, skipping")
        return

    print("-> Sending to S3")
    user = os.getenv("AWS_ACCESS_KEY_ID")
    bucket = os.getenv("AWS_BUCKET", "ufk")
    minio_client = boto3.client(
        "s3",
        endpoint_url=s3_endpoint,
        aws_access_key_id=user,
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )
    for seo_file, seo_file_ct in [
        ("sitemap.xml", "application/xml"),
        ("robots.txt", "text/plain"),
    ]:
        minio_client.upload_file(
            Filename=f"dist/{site_env_path}/{seo_file}",
            Bucket=bucket,
            Key=f"{site_env_path}/{seo_file}",
            ExtraArgs={'ContentType': f'{seo_file_ct}; charset=utf-8'}
        )
    print("-> Sent to S3")

    print(f"-> Listing contents of bucket '{bucket}':")
    response = minio_client.list_objects_v2(Bucket=bucket)
    if "Contents" in response:
        for obj in response["Contents"]:
            print(
                f"  - {obj.get('Key')} (Size: {obj.get('Size')} bytes, Modified: {obj.get('LastModified')})"
            )
    else:
        print("  No objects found in bucket")


def generate():
    # this will fail naturally if config is not proper
    config, site_env_path = parse_config()
    urls = fetch_urls(config)
    create_sitemap(urls, site_env_path)
    print(f"-> Created sitemap.xml with {len(urls)} urls")
    create_robots(config, site_env_path, has_sitemap=bool(urls))
    print("-> Created robots.txt")
    send_to_s3(site_env_path)


if __name__ == "__main__":
    generate()
