import requests
# import json

from OSMPythonTools.nominatim import Nominatim


def test_nominatim_query():
    nominatim = Nominatim()
    osm_data = nominatim.query(
        "Riga, Latvia", params={'accept-language': 'en', '4': 'riga'})
    json = osm_data.toJSON()[0]
    assert json is not None
    assert 'lon' in json
    assert 'lat' in json
    assert json['name'] == "Riga"


def fetch_overpass(query):
    url = "https://overpass-api.de/api/interpreter"
    # url = "https://maps.mail.ru/osm/tools/overpass/api/interpreter"
    # url = "https://overpass.private.coffee/api/interpreter"
    # headers = {
    #     "User-Agent":
    #       "EarthCrawlerApp/2.0.0 (https://github.com/ikomash/earth-crawler)",
    # }
    headers = {
        "User-Agent":
            "MyOSMTools/1.0 (https://github.com/yourname/MyOSMTools)",
    }
    response = requests.post(
        url, data={'data': query}, headers=headers, timeout=600)
    response.raise_for_status()
    return response.json()


if __name__ == "__main__":
    # query = '[out:json][timeout:600];'\
    #     'area(3600060189)->.country; relation["boundary"="administrative"]'\
    #     '["admin_level"~"^(4)$"](area.country); out body geom;'
    query = '[out:json][timeout:600];'\
        'area(3613048688)->.country; relation["boundary"="administrative"]'\
        '["admin_level"~"^(4)$"](area.country); out body geom;'
    data = fetch_overpass(query)
    print(len(data['elements']))
