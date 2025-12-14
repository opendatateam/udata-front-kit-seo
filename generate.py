import os
from enum import StrEnum
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


class PageAPI(StrEnum):
    """Maps config keys to API endpoints"""
    topics_pages = "2/topics"
    datasets_pages = "2/datasets"
    dataservices_pages = "1/dataservices"


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
    for page in (getattr(config.website.seo.sitemap_xml, page_api.name) or []):
        print(f"-> {page_api.name}: {page!r}")
        query = config.pages[page].universe_query
        for remote_object in iter_pages(f"{config.datagouvfr.base_url}/api/{page_api.value}/", params=query):
            results.append({
                "url": f"{config.website.seo.canonical_url}/{page}/{remote_object['slug']}",
                "last_modified": datetime.fromisoformat(remote_object["last_modified"]),
            })
    return results


def fetch_urls(config: Config) -> list[SitemapUrl]:
    results: list[SitemapUrl] = []

    if not config.website.seo.sitemap_xml:
        print("-> no sitemap.xml config, skipping")
        return []

    # handle topics
    results += fetch_urls_for_page(PageAPI.topics_pages, config)

    # handle datasets
    results += fetch_urls_for_page(PageAPI.datasets_pages, config)

    # handle dataservices
    results += fetch_urls_for_page(PageAPI.dataservices_pages, config)

    # handle static pages
    # 1. homepage
    static_urls = ["/"]
    # 2. static pages
    static_urls += [p.route for p in config.website.router.static_pages or []]
    # 3. objects list pages
    for page_api in PageAPI:
        pages = getattr(config.website.seo.sitemap_xml, page_api.name) or []
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

    # TODO: has disallow / based on meta.robots contains noindex?

    if has_sitemap:
        content += f"\nSitemap: {config.website.seo.canonical_url}/sitemap.xml"

    site_env_dir = Path(f"dist/{site_env_path}")
    site_env_dir.mkdir(parents=True, exist_ok=True)

    robots_file = site_env_dir / "robots.txt"
    robots_file.write_text(content)


def generate():
    # this will fail naturally if config is not proper
    config, site_env_path = parse_config()
    urls = fetch_urls(config)
    # TODO: or maybe keep the empty sitemap?
    if urls:
        create_sitemap(urls, site_env_path)
        print(f"-> Created sitemap.xml with {len(urls)} urls")
    create_robots(config, site_env_path, has_sitemap=bool(urls))
    print("-> Created robots.txt")
    if (s3_endpoint := os.getenv("AWS_ENDPOINT_URL")):
        print("-> Sending to S3")
        bucket = os.getenv("AWS_ACCESS_KEY_ID")
        minio_client = boto3.client(
            "s3",
            endpoint_url=s3_endpoint,
            aws_access_key_id=bucket,
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        )
        # TODO: what about removing/emptying?
        if len(urls):
            minio_client.upload_file(
                Filename=f"dist/{site_env_path}/sitemap.xml",
                Bucket=bucket,
                Key=f"{site_env_path}/sitemap.xml",
                ExtraArgs={'ContentType': 'application/xml; charset=utf-8'}
            )
        minio_client.upload_file(
            Filename=f"dist/{site_env_path}/robots.xml",
            Bucket=bucket,
            Key=f"{site_env_path}/robots.xml",
            ExtraArgs={'ContentType': 'application/xml; charset=utf-8'}
        )
        print("-> Sent to S3")


if __name__ == "__main__":
    generate()
