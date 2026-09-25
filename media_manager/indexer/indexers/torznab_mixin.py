import logging
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from media_manager.indexer.schemas import IndexerQueryResult

log = logging.getLogger(__name__)


class TorznabMixin:
    def process_search_result(self, xml: str) -> list[IndexerQueryResult]:
        result_list: list[IndexerQueryResult] = []
        xml_tree = ET.fromstring(xml)  # noqa: S314  # trusted source, since it is user controlled
        xmlns = {
            "torznab": "http://torznab.com/schemas/2015/feed",
            "atom": "http://www.w3.org/2005/Atom",
        }
        for item in xml_tree.findall("channel/item"):
            try:
                flags: list[str] = []
                seeders = 0
                age = 0
                indexer_name = "unknown"

                jackett_indexer = item.find("jackettindexer")
                prowlarr_indexer = item.find("prowlarrindexer")
                if jackett_indexer is not None and jackett_indexer.text:
                    indexer_name = jackett_indexer.text
                if prowlarr_indexer is not None and prowlarr_indexer.text:
                    indexer_name = prowlarr_indexer.text

                enclosure = item.find("enclosure")
                if enclosure is None:
                    log.warning("Torznab item has no enclosure, skipping.")
                    continue

                is_usenet = enclosure.attrib.get("type") != "application/x-bittorrent"

                attributes = list(item.findall("torznab:attr", xmlns))
                for attribute in attributes:
                    if is_usenet:
                        if attribute.attrib["name"] == "usenetdate":
                            posted_date = parsedate_to_datetime(
                                attribute.attrib["value"]
                            )
                            now = datetime.now(UTC)
                            age = int((now - posted_date).total_seconds())
                    else:
                        if attribute.attrib["name"] == "seeders":
                            seeders = int(attribute.attrib["value"])

                        if attribute.attrib["name"] == "downloadvolumefactor":
                            download_volume_factor = float(attribute.attrib["value"])
                            if download_volume_factor == 0:
                                flags.append("freeleech")
                            if download_volume_factor == 0.5:
                                flags.append("halfleech")
                            if download_volume_factor == 0.75:
                                flags.append("freeleech75")
                            if download_volume_factor == 0.25:
                                flags.append("freeleech25")

                        if attribute.attrib["name"] == "uploadvolumefactor":
                            upload_volume_factor = float(attribute.attrib["value"])
                            if upload_volume_factor == 2:
                                flags.append("doubleupload")

                title_element = item.find("title")
                title = (
                    title_element.text
                    if title_element is not None and title_element.text
                    else "unknown"
                )
                size_str = item.find("size")
                if size_str is None or size_str.text is None:
                    log.warning(f"Torznab item {title} has no size, skipping.")
                    continue
                try:
                    size = int(size_str.text or "0")
                except ValueError:
                    log.warning(f"Torznab item {title} has invalid size, skipping.")
                    continue

                result = IndexerQueryResult(
                    title=title,
                    download_url=str(enclosure.attrib["url"]),
                    seeders=seeders,
                    flags=flags,
                    size=size,
                    usenet=is_usenet,
                    age=age,
                    indexer=indexer_name,
                )
                result_list.append(result)
            except Exception:
                log.exception("1 Torznab search result failed")
        return result_list
