import os
from enum import StrEnum
import email.utils

from datetime import datetime, UTC
from typing import TypedDict
from xml.etree import ElementTree

import boto3
import requests

from config import parse_config, Config


class SitemapUrl(TypedDict):
    url: str
    last_modified: datetime


class PageAPI(StrEnum):
    topics_pages = "/topics"
    datasets_pages = "/datasets"
    dataservices_pages = "/dataservices"


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
        for remote_object in iter_pages(f"{config.datagouvfr.base_url}/api/2/{page_api.value}/", params=query):
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
    for relative_url in (config.website.seo.sitemap_xml.static_urls or []):
        static_url = f"{config.website.seo.canonical_url}{relative_url}"
        r = requests.get(static_url)
        r.raise_for_status()
        results.append({
            "url": static_url,
            "last_modified": parse_http_date_with_tz(
                r.headers['last-modified']
            ),
        })

    return results


# TODO: make this env/site compatible
def create_sitemap(urls: list[SitemapUrl], write: bool = True) -> str:
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
    if write:
        tree.write("dist/sitemap.xml")
        return ""
    else:
        return ElementTree.tostring(tree.getroot(), encoding="unicode") # type: ignore (wrong stubs)


def generate(write: bool = True) -> str:
    # this will fail naturally if config is not proper
    config = parse_config()
    urls = fetch_urls(config)
    res = create_sitemap(urls, write=write)
    if (s3_endpoint := os.getenv("AWS_ENDPOINT_URL")):
        bucket = os.getenv("AWS_ACCESS_KEY_ID")
        minio_client = boto3.client(
            "s3",
            endpoint_url=s3_endpoint,
            aws_access_key_id=bucket,
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        )
        minio_client.upload_file(
            Filename="dist/sitemap.xml",
            Bucket=bucket,
            Key="sitemap.xml",
            ExtraArgs={'ContentType': 'application/xml; charset=utf-8'}
        )
    return res


if __name__ == "__main__":
    generate()
