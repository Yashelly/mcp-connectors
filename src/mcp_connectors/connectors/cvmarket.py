from urllib.parse import parse_qs, urlencode, urlsplit

from bs4 import BeautifulSoup

from ..errors import ConnectorError
from ..models import JobListing, JobSearch, Salary
from ..parsing import clean, json_nodes, require_title, requirements, salary, text_at
from .base import Connector, ConnectorInfo, ParsedPage


class CVmarketConnector(Connector):
    info = ConnectorInfo("cvmarket", "CVmarket", "https://www.cvmarket.lt", "jobs", live_status="passed", last_live_check="2026-09-21", live_browser="visible-chrome")
    listing_pattern = r"/[^/]+-\d{7,}/?"
    filters = ("query", "city")
    cities = {"Vilnius": 134, "Kaunas": 135, "Klaipėda": 136, "Šiauliai": 137, "Panevėžys": 138}

    def search_url(self, options: JobSearch, page: int):
        params = {"op": "search", "search[keyword]": options.query}
        # The site's start=0 redirect double-encodes bracketed filter names.
        if page > 1:
            params["start"] = (page - 1) * 30
        if options.city:
            params["search[locations][]"] = self.cities[options.city]
        return self.info.website + "/darbo-skelbimai?" + urlencode(params)

    def parse_search(self, html, url, page):
        soup = self.soup(html)
        items = [JobListing(source=self.info.id, url=self.listing_url(node["href"], relative=True),
                 title=require_title(text_at(node, "h2")), company=text_at(node, ".job-company"),
                 location=text_at(node, "span.location"), salary=salary(text_at(node, ".salary-block")))
                 for node in soup.select("a.jobad-url")]
        if not items:
            self.empty_or_changed(soup, ("Skelbimų su Jūsų pasirinktais kriterijais šiuo metu nėra",))
        more = any(parse_qs(urlsplit(a["href"]).query).get("start") == [str(page * 30)] for a in soup.select("a[href]"))
        return ParsedPage(items, more)

    def parse_listing(self, html, url):
        soup = self.soup(html)
        nodes = json_nodes(soup)
        job = next((n for n in nodes if n.get("@type") == "JobPosting"), None)
        if not job:
            raise ConnectorError("layout_changed", "Public JobPosting JSON-LD is missing")
        refs = {}
        for node in nodes:
            key = node.get("@id")
            if key and len(node) > len(refs.get(key, {})):
                refs[key] = node
        def resolve(value):
            if not isinstance(value, dict):
                return {}
            key = value.get("@id", "")
            # Live JSON-LD uses PostalAddress in references but Address in definitions.
            resolved = refs.get(key, value)
            if len(resolved) == 1:
                resolved = refs.get(key.replace("#/schema/PostalAddress/", "#/schema/Address/"), resolved)
            return resolved
        organization = resolve(job.get("hiringOrganization"))
        locations = job.get("jobLocation", [])
        if isinstance(locations, dict):
            locations = [locations]
        places = []
        for loc in locations:
            address = resolve(resolve(loc).get("address"))
            places.extend((clean(address.get("addressLocality") or address.get("addressRegion")), clean(address.get("addressCountry"))))
        pay = job.get("baseSalary") or {}
        value = pay.get("value") or {}
        if not isinstance(value, dict):
            value = {"value": value}
        desc = job.get("description") or ""
        raw = next((clean(n.parent) for n in soup.select("b") if "€/mėn." in (clean(n.parent) or "")), None)
        amount = Salary(minimum=value.get("minValue", value.get("value")), maximum=value.get("maxValue", value.get("value")),
                        currency=pay.get("currency"), period=value.get("unitText"), raw=raw) if pay else None
        return JobListing(source=self.info.id, url=url, title=require_title(clean(job.get("title"))),
            company=clean(organization.get("name")) or text_at(soup, 'a[data-track^="emp_profile_click,emp_click_header,"]'),
            location=", ".join(dict.fromkeys(filter(None, places))) or None,
            salary=amount, description=clean(BeautifulSoup(desc, "html.parser")), requirements=requirements(desc),
            date_posted=job.get("datePosted"))
