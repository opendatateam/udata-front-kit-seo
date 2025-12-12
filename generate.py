import os
from dataclasses import dataclass
from enum import StrEnum
import email.utils

from datetime import datetime, UTC
from typing import TypedDict
from xml.etree import ElementTree

import boto3
import dacite
import requests
import yaml



@dataclass
class MetaConfig:
    keywords: str | None = None
    description: str | None = None
    robots: str | None = None

@dataclass
class RobotsTxtConfig:
    disallow: list[str] | None = None

@dataclass
class SitemapXmlConfig:
    topics_pages: list[str] | None = None
    datasets_pages: list[str] | None = None
    dataservices_pages: list[str] | None = None
    static_urls: list[str] | None = None

@dataclass
class SeoConfig:
    canonical_url: str
    meta: MetaConfig | None = None
    sitemap_xml: SitemapXmlConfig | None = None
    robots_txt: RobotsTxtConfig | None = None

@dataclass
class PageConfig:
    universe_query: dict

@dataclass
class DatagouvfrConfig:
    base_url: str

@dataclass
class WebsiteConfig:
    seo: SeoConfig

@dataclass
class Config:
    website: WebsiteConfig
    datagouvfr: DatagouvfrConfig
    pages: dict[str, PageConfig]


class DeployEnv(StrEnum):
    PROD = 'prod'
    PREPROD = 'preprod'
    DEMO = 'demo'

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


# TODO: move config parsing/setup to own function
def fetch_urls() -> list[SitemapUrl]:
    deploy_env = DeployEnv(os.getenv("ENV"))
    print(f"-> env: {deploy_env.value!r}")

    site = os.getenv("SITE")

    if not site:
        raise ValueError("SITE env var not set.")

    gh_branch = f"{site}-{deploy_env}"
    gh_url = f"https://raw.githubusercontent.com/opendatateam/udata-front-kit/refs/heads/{gh_branch}/configs/{site}/config.yaml"
    # FIXME: test commit
    gh_url = "https://raw.githubusercontent.com/opendatateam/udata-front-kit/f453959f0c8e44804bd65e90b6f3fc342d3962dd/configs/ecospheres/config.yaml"

    r = requests.get(gh_url)
    if not r.ok:
        raise ValueError(f"Could not fetch config from {gh_url}")

    config_dict = yaml.safe_load(r.text)
    try:
        config = dacite.from_dict(Config, config_dict)
    except dacite.DaciteError as e:
        print(f"❌ Error parsing conf for {gh_branch}: {e}")
        return []

    print(f"-> site: {site!r}")
    print(f"-> config url: {gh_url!r}")
    print(f"-> seo config:\n{yaml.dump(config_dict['website']['seo'], default_flow_style=False, indent=2)}")

    site_url = config.website.seo.canonical_url
    print(f"-> base url: {site_url!r}")

    datagouvfr_url = config.datagouvfr.base_url
    print(f"-> data.gouv.fr url: {datagouvfr_url!r}")

    results: list[SitemapUrl] = []

    if not config.website.seo.sitemap_xml:
        print("-> no sitemap.xml config, skipping")
        return []

    # handle topics
    # TODO: make this a fn
    for t_page in (config.website.seo.sitemap_xml.topics_pages or []):
        print(f"-> topic page: {t_page!r}")
        query = config.pages[t_page].universe_query
        for topic in iter_pages(f"{datagouvfr_url}/api/2/topics/", params=query):
            results.append({
                "url": f"{site_url}/{t_page}/{topic['slug']}",
                "last_modified": datetime.fromisoformat(topic["last_modified"]),
            })

    # handle datasets
    for t_page in (config.website.seo.sitemap_xml.datasets_pages or []):
        print(f"-> dataset page: {t_page!r}")
        query = config.pages[t_page].universe_query
        for topic in iter_pages(f"{datagouvfr_url}/api/2/datasets/", params=query):
            results.append({
                "url": f"{site_url}/{t_page}/{topic['slug']}",
                "last_modified": datetime.fromisoformat(topic["last_modified"]),
            })

    # handle dataservices
    for t_page in (config.website.seo.sitemap_xml.dataservices_pages or []):
        print(f"-> dataservice page: {t_page!r}")
        query = config.pages[t_page].universe_query
        for topic in iter_pages(f"{datagouvfr_url}/api/2/dataservices/", params=query):
            results.append({
                "url": f"{site_url}/{t_page}/{topic['slug']}",
                "last_modified": datetime.fromisoformat(topic["last_modified"]),
            })

    # handle static pages
    for relative_url in (config.website.seo.sitemap_xml.static_urls or []):
        static_url = f"{site_url}{relative_url}"
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
