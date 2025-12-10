import os
import email.utils

from datetime import datetime, UTC
from typing import TypedDict
from xml.etree import ElementTree

import boto3
import requests

ENV = os.getenv("ENV", "www")
ECOSPHERES_URL = (
    "https://demo.ecologie.data.gouv.fr"
    if ENV == "demo"
    else "https://ecologie.data.gouv.fr"
)
DATAGOUVFR_URL = f"https://{ENV}.data.gouv.fr/api"
UNIVERSE_NAME = "ecospheres" if ENV == "demo" else "univers-ecospheres"

INDICATEURS_ORG = "67884b4da4fca9c97bbef479"
INDICATEURS_QUERY = {
    "tag": "ecospheres-indicateurs",
    "organization": INDICATEURS_ORG,
}

STATIC_URLS = [
    "/",
    "/bouquets",
    "/indicators",
    "/about",
]


class SitemapUrl(TypedDict):
    url: str
    last_modified: datetime


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


def fetch_urls() -> list[SitemapUrl]:
    results = []

    # static urls
    for url in STATIC_URLS:
        page_url = f"{ECOSPHERES_URL}{url}"
        r = requests.get(page_url)
        r.raise_for_status()
        results.append({
            "url": page_url,
            "last_modified": parse_http_date_with_tz(
                r.headers['last-modified']
            ),
        })

    # bouquets
    for bouquet in iter_pages(f"{DATAGOUVFR_URL}/2/topics/", params={
        "tag": UNIVERSE_NAME,
    }):
        results.append({
            "url": f"{ECOSPHERES_URL}/bouquets/{bouquet['slug']}",
            "last_modified": datetime.fromisoformat(bouquet["last_modified"]),
        })

    # indicators
    for indicator in iter_pages(f"{DATAGOUVFR_URL}/2/datasets/", params=INDICATEURS_QUERY):
        results.append({
            "url": f"{ECOSPHERES_URL}/indicators/{indicator['id']}",
            "last_modified": datetime.fromisoformat(indicator["last_modified"]),
        })

    return results


def create_sitemap(urls, write=True) -> str:
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


def generate(write=True) -> str:
    urls = fetch_urls()
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
