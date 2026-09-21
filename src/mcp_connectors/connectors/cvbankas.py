from urllib.parse import urlencode, parse_qs, urlsplit

from ..models import JobListing, JobSearch
from ..parsing import clean, require_title, requirements, salary, text_at
from .base import Connector, ConnectorInfo, ParsedPage


class CVbankasConnector(Connector):
    info = ConnectorInfo("cvbankas", "CVbankas", "https://www.cvbankas.lt", "jobs", live_status="passed", last_live_check="2026-09-21")
    listing_pattern = r"/[^/]+/1-\d+/?"
    filters = ("query", "city")
    cities = {"Vilnius": 606, "Kaunas": 530, "Klaipėda": 538, "Šiauliai": 581, "Panevėžys": 560}

    def search_url(self, options: JobSearch, page: int):
        params = {"keyw": options.query, "page": page}
        if options.city:
            params["location[]"] = self.cities[options.city]
        return self.info.website + "/?" + urlencode(params)

    def parse_search(self, html, url, page):
        soup = self.soup(html)
        items = []
        for node in soup.select("a.list_a"):
            items.append(JobListing(source=self.info.id, url=self.listing_url(node["href"], relative=True),
                title=require_title(text_at(node, ".list_h3")), company=text_at(node, ".heading_secondary"),
                location=text_at(node, ".list_city"), salary=salary(text_at(node, ".salary_inner"))))
        if not items:
            self.empty_or_changed(soup, ("Skelbimų pagal Jūsų pasirinktus kriterijus nėra",))
        has_more = any(parse_qs(urlsplit(a.get("href", "")).query).get("page") == [str(page + 1)]
                       for a in soup.select('a[href], link[rel="next"]'))
        return ParsedPage(items, has_more)

    def parse_listing(self, html, url):
        soup = self.soup(html)
        description = soup.select_one('[itemprop="description"]')
        date = soup.select_one('meta[itemprop="datePosted"]')
        return JobListing(source=self.info.id, url=url, title=require_title(text_at(soup, "#jobad_heading1")),
            company=text_at(soup, "#jobad_company_title"), location=text_at(soup, '#jobad_location [itemprop="addressLocality"]'),
            salary=salary(text_at(soup, "#jobad_header .salary_component .label_component_body")),
            description=clean(description), requirements=requirements(str(description)) if description else None,
            date_posted=date.get("content") if date else None)
