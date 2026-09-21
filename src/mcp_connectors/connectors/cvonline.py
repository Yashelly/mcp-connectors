import json
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from ..errors import ConnectorError
from ..models import JobListing, JobSearch, Salary
from ..parsing import clean, require_title, requirements
from .base import Connector, ConnectorInfo, ParsedPage


class CVonlineConnector(Connector):
    info = ConnectorInfo("cvonline", "CVonline", "https://www.cvonline.lt", "jobs", live_status="passed", last_live_check="2026-09-21", live_browser="visible-chrome")
    listing_pattern = r"/(?:lt/)?vacancy/\d+(?:/[^/]+){0,2}/?"
    filters = ("query", "city")
    cities = {"Vilnius": 540, "Kaunas": 501, "Klaipėda": 505, "Šiauliai": 528, "Panevėžys": 517}

    def search_url(self, options: JobSearch, page: int):
        params = {"limit": 20, "offset": (page - 1) * 20}
        if options.city:
            params["towns[0]"] = self.cities[options.city]
        if options.query:
            params["keywords[0]"] = options.query
        return self.info.website + "/lt/search?" + urlencode(params)

    def props(self, soup):
        node = soup.select_one("script#__NEXT_DATA__")
        try:
            return json.loads(node.string)["props"]["pageProps"]
        except (AttributeError, KeyError, ValueError, TypeError) as error:
            raise ConnectorError("layout_changed", "CVonline page data is missing or invalid") from error

    def location(self, item, locations):
        names = []
        for key, group in (("townId", "towns"), ("countryId", "countries")):
            values = locations.get(group, {})
            if isinstance(values, list):
                values = {str(value["id"]): value for value in values if isinstance(value, dict) and "id" in value}
            names.append(clean(values.get(str(item.get(key)), {}).get("name")))
        return ", ".join(dict.fromkeys(filter(None, names))) or None

    def parse_search(self, html, url, page):
        soup = self.soup(html)
        props = self.props(soup)
        data = props.get("searchResults")
        if not isinstance(data, dict) or not isinstance(data.get("vacancies"), list) or not isinstance(data.get("total"), int):
            raise ConnectorError("layout_changed", "CVonline searchResults payload is missing or malformed")
        locations = props.get("initialState", {}).get("locations", {})
        items = []
        for item in data["vacancies"]:
            link = soup.select_one(f'a[data-testid="vacancy-item-link-title-{item["id"]}"]')
            if not link:
                raise ConnectorError("layout_changed", "CVonline vacancy link is missing")
            pay = None
            if item.get("salaryFrom") is not None or item.get("salaryTo") is not None:
                pay = Salary(minimum=item.get("salaryFrom"), maximum=item.get("salaryTo"))
                # Currency comes from visible listing text, never from locale inference.
                card = link.find_parent(class_="vacancy-item")
                pay_node = card.select_one(".salary-label") if card else None
                pay.raw = clean(pay_node)
                if pay.raw and "€" in pay.raw:
                    pay.currency = "EUR"
                if item.get("hourlySalary") is True:
                    pay.period = "HOUR"
            items.append(JobListing(source=self.info.id, url=self.listing_url(link["href"], relative=True),
                title=require_title(clean(item.get("positionTitle"))), company=clean(item.get("employerName")),
                location=self.location(item, locations), salary=pay,
                description=clean(item.get("positionContent")), date_posted=item.get("publishDate"),
                requirements=[clean(x) for x in item.get("skills") or [] if clean(x)] or None))
        if not items and data["total"] > (page - 1) * 20:
            raise ConnectorError("layout_changed", "Nonzero result count without vacancy records")
        return ParsedPage(items, page * 20 < data["total"])

    def parse_listing(self, html, url):
        soup = self.soup(html)
        props = self.props(soup)
        vacancy = props.get("vacancy", {})
        key = url.split("/vacancy/")[1].split("/")[0]
        item = vacancy.get(key)
        if not isinstance(item, dict):
            raise ConnectorError("layout_changed", "Requested vacancy payload is missing")
        highlights = item.get("highlights") or {}
        sections = (item.get("details") or {}).get("standardDetails") or []
        if not isinstance(sections, list):
            raise ConnectorError("layout_changed", "Unexpected vacancy description format")
        fragment = "".join(f'<h2>{s.get("title") or ""}</h2>{s.get("content") or ""}' for s in sections)
        pay = None
        if highlights.get("salaryFrom") is not None or highlights.get("salaryTo") is not None:
            pay = Salary(minimum=highlights.get("salaryFrom"), maximum=highlights.get("salaryTo"),
                         period={"MONTHLY": "MONTH", "HOURLY": "HOUR"}.get(highlights.get("ratePer")))
            # Detail salary text is populated below from the observed DOM selector.
            salary_node = soup.select_one(".vacancy-highlights__salary")
            if salary_node:
                pay.raw = clean(salary_node)
                pay.currency = "EUR" if "€" in pay.raw else None
        return JobListing(source=self.info.id, url=url, title=require_title(clean(item.get("position"))),
            company=clean(item.get("employerName")), location=self.location(highlights.get("location") or {}, props.get("locations") or {}),
            salary=pay, description=clean(BeautifulSoup(fragment, "html.parser")), requirements=requirements(fragment),
            date_posted=item.get("firstPublishDate"))
