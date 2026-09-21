from urllib.parse import urlencode, parse_qs, urlsplit

from ..models import CarListing, CarSearch
from ..parsing import clean, text_at, require_title
from .base import Connector, ConnectorInfo, ParsedPage
from .car_parsing import make_model, mileage, parameter_values, price_fields, year


class AutopliusConnector(Connector):
    info = ConnectorInfo("autoplius", "Autoplius", "https://autoplius.lt", "cars", live_status="blocked", last_live_check="2026-09-21")
    listing_pattern = r"/skelbimai/[^/]+-\d+\.html"
    filters = ("query", "price_from", "price_to", "year_from", "year_to")

    def search_url(self, options: CarSearch, page: int):
        params = {"page_nr": page}
        for field, key in (("query", "qt"), ("price_from", "sell_price_from"), ("price_to", "sell_price_to"),
                           ("year_from", "make_date_from"), ("year_to", "make_date_to")):
            value = getattr(options, field)
            if value is not None and value != "":
                params[key] = value
        return self.info.website + "/skelbimai/naudoti-automobiliai?" + urlencode(params)

    def parse_search(self, html, url, page):
        soup = self.soup(html)
        items = []
        for node in soup.select("a.announcement-item"):
            title = require_title(text_at(node, ".announcement-title"))
            make, model = make_model(title)
            values = [clean(n) for n in node.select(".announcement-parameters-block span") if clean(n)]
            location = values[-1] if values and all(v is None for v in parameter_values([values[-1]]).values()) else None
            items.append(CarListing(source=self.info.id, url=self.listing_url(node["href"], relative=True),
                title=title, make=make, model=model, year=year(text_at(node, ".announcement-title-parameters")),
                location=location,
                **price_fields(text_at(node, ".announcement-pricing-info > strong")), **parameter_values(values)))
        if not items:
            self.empty_or_changed(soup, ("Pagal šiuos paieškos kriterijus skelbimų nerasta",))
        more = any(parse_qs(urlsplit(a["href"]).query).get("page_nr") == [str(page + 1)] for a in soup.select('a[rel="next"][href]'))
        return ParsedPage(items, more)

    def parse_listing(self, html, url):
        soup = self.soup(html)
        title = require_title(text_at(soup, ".title-text"))
        fields = {text_at(n, ".parameter-label"): text_at(n, ".parameter-value") for n in soup.select(".parameter-row")}
        crumbs = [n for n in soup.select("li.crumb a") if "/skelbimai/naudoti-automobiliai/" in n.get("href", "")]
        price = soup.select_one(".price")
        if price:
            for extra in price.select(".cash-usage-limit-container"):
                extra.decompose()
        return CarListing(source=self.info.id, url=url, title=title,
            make=clean(crumbs[0]) if crumbs else None, model=clean(crumbs[1]) if len(crumbs) > 1 else None,
            year=year(fields.get("Pirma registracija")), fuel=fields.get("Kuro tipas"), transmission=fields.get("Pavarų dėžė"),
            mileage_km=mileage(fields.get("Rida")), engine=fields.get("Variklis"),
            description=text_at(soup, ".announcement-description"), location=text_at(soup, ".seller-contact-location-content"),
            **price_fields(clean(price)))
