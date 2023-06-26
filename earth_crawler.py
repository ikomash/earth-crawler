from OSMPythonTools.nominatim import Nominatim
from OSMPythonTools.overpass import overpassQueryBuilder, Overpass
import simplekml
from shapely import wkt
import pandas as pd
import os
from tempdata import TempData
# imports for types
from shapely.geometry.polygon import Polygon
from OSMPythonTools.element import Element as OSMElement
from OSMPythonTools.overpass import OverpassResult


def pause():  # !remove
    os.system('pause')


class EarthCrawler():
    """
    Uses OSM APIs (Nominatim, Overpass) to get requested regions and
    countries borders as well as various lacalities (cities, towns, villages,
    etc.) and export them to related formats (kml, xlsx).
    """
    def __init__(self, Tmp: TempData) -> None:
        """
        Initializes OSM APIs instances and resieves temporary data
        class instance.

        Args:
            Tmp (TempData): Temporary data class instance
        """
        # Settings import
        self.Tmp = Tmp

        # Initiate search engine
        self.nominatim = Nominatim()
        self.overpass = Overpass()

    def admin_level_try_list_creator(
            self, target_val: int, values_list: list) -> list:
        """
        Creates 'try list' of administrative levels, to parse through with
        additional user-defined value as the first element.

        Args:
            target_val (int): user-defined value
            values_list (list): basic 'try list'

        Returns:
            list: final 'try list'
        """
        output_list = [target_val]
        for i in values_list:
            if i != target_val:
                output_list.append(i)
        return output_list

    def configure_kml_obj(self, kml_obj: simplekml.Folder) -> simplekml.Folder:
        """Sets kml lines color and width.

        Args:
            kml_obj (simplekml.Folder): Base kml folder object

        Returns:
            simplekml.Folder: Configured kml folder object
        """
        kml_obj.style.linestyle.color = simplekml.Color.hex(
            self.Tmp.line_color[1:])
        kml_obj.style.linestyle.width = self.Tmp.line_width
        return kml_obj

    def add_kml_object(
            self, kml_level: simplekml.Folder, coords: list,
            obj_name: str, obj_types: list) -> None:
        """
        Adds an object with the specified coordinates, name and type to
        the specific folder.

        Args:
            kml_level (simplekml.Folder): Kml folder to add objects to
            coords (list): Object coordinates
            obj_name (str): Object name
            obj_types (list): Object type: 'Polygon' or 'Line'
        """
        if 'Polygon' in obj_types and self.Tmp.polygons_to_lines is False:
            kml_obj = kml_level.newpolygon(
                name=f"{obj_name}", outerboundaryis=coords)
            kml_obj.polystyle.fill = 0
            self.configure_kml_obj(kml_obj)
        if 'Line' in obj_types or self.Tmp.polygons_to_lines is True:
            kml_obj = kml_level.newlinestring(
                name=f"{obj_name}", coords=coords)
            self.configure_kml_obj(kml_obj)

    def choose_name_from_tag(self, tags: dict) -> str:
        """
        Chooses object name according to selected language. If there is
        no such object name language in OSM data, chooses default one from
        "name" tag.

        Args:
            tags (dict): Tags from nominatim search results

        Returns:
            str: Object name
        """
        cur_lang_tag = f"name:{self.Tmp.objects_language}"
        if cur_lang_tag in tags:  # f"name:{cur_lang_tag}"
            return tags[cur_lang_tag]
        elif "neme:en" in tags:
            return tags["neme:en"]
        else:
            return tags["name"]

    def proccess_loaded_wkt(self, kml_doc: simplekml.Folder,
                            loaded_wkt: Polygon) -> None:
        """
        Checks if the loaded wkt (well-known text) is polygon or multi-polygon
        object and passes it's coordinates to 'add_kml_object' function.

        Args:
            kml_doc (simplekml.Folder):
                Kml folder object
            loaded_wkt (Polygon):
                Wkt returned by Nominatim API
        """
        if loaded_wkt.geom_type == 'MultiPolygon':
            polygons = list(loaded_wkt.geoms)
            multi_poly_folder = kml_doc.newfolder(
                name=f"{self.Tmp.current_sub_obj_name}")
            for i, poly in enumerate(polygons):
                coords = list(poly.exterior.coords)
                i_obj_name = f"{self.Tmp.current_sub_obj_name}_{i+1}"
                # if len(coords) > 5000:
                self.add_kml_object(
                    multi_poly_folder, coords, i_obj_name, ['Polygon'])
        elif loaded_wkt.geom_type == 'Polygon':
            coords = list(loaded_wkt.exterior.coords)
            self.add_kml_object(
                kml_doc, coords, self.Tmp.current_sub_obj_name, ['Polygon'])

    def save_kml(self, obj_name: str) -> None:
        """Saves kml file.

        Args:
            obj_name (str): Object name used in file name
        """
        if self.Tmp.polygons_to_lines:
            sub_name = "(lines)"
        else:
            sub_name = "(polygons)"
        kml_file_name = f"{obj_name} {sub_name}"
        self.kml_doc.save(f".\\exports\\{kml_file_name}.kml")
        print(f"KML file saved as {kml_file_name}")

    def save_excel(self, obj_name: str) -> None:
        """Save Excel 'xlsx' file.

        Args:
            obj_name (str): Object name used in file name
        """
        self.excel_writer.close()
        print(f"Excel file saved {self.Tmp.current_obj_name}.xlsx.xlsx")

    def search_line_proccessing(self) -> list[tuple[str, int]]:
        """
        Splits string with objects to search (and their administrative levels)
        and creates a search list of [object name (str), administrative level
        (int)] tuples.

        Returns:
            list(tuple(str,int)): Search list of (object name (str),
                administrative level (int)) tuples
        """
        # search_list = list(map(str.strip, search_line.split(';')))
        search_list = []
        first_split_lst = self.Tmp.search_line.split(';')
        for loc in first_split_lst:
            strp = loc.strip()
            if strp != "":
                if "=" in strp:
                    loc_lst = strp.split('=')
                    loc_tuple = (loc_lst[0], int(loc_lst[1]))
                else:
                    loc_tuple = (strp, 4)
                search_list.append(loc_tuple)
        return search_list

    def regions_search(self, index: int, region: OSMElement,
                       kml_doc: simplekml.Folder) -> None:
        """Searches region polygons returned by Nominatim

        Args:
            index (int): Index used to track progress
            region (OSMElement): Element, found by Nominatim
            kml_doc (simplekml.Folder): Kml folder object
        """
        self.Tmp.current_stage = 0
        self.Tmp.current_stage_num += 1
        self.Tmp.current_obj = index
        self.Tmp.current_area_obj = index
        self.Tmp.current_area_obj_name = region.tag(
            f'name:{self.Tmp.objects_language}')
        self.Tmp.current_sub_obj_name = region.tag(
            f'name:{self.Tmp.objects_language}')
        region_data = self.nominatim.query(
            f"{region.type()}/{region.id()}",
            zoom=4, lookup=True, wkt=True)
        loaded_wkt = wkt.loads(region_data.wkt())
        if hasattr(loaded_wkt, 'geom_type'):
            self.proccess_loaded_wkt(kml_doc, loaded_wkt)
        else:
            print("No attr")

    def locations_search(self, index: int, region: OSMElement,
                         kml_doc: simplekml.Folder) -> None:
        """Searches location points returned by Nominatim

        Args:
            index (int): Index used to track progress
            region (OSMElement): Element, found by Nominatim
            kml_doc (simplekml.Folder): Kml folder object
        """
        self.Tmp.current_stage = 1
        self.Tmp.current_stage_num += 1
        keys_list = self.Tmp.search_places_choice + \
            ["county", "state", "region", "country"]
        points = self.overpass.query
        dict_list = []
        points_search_line = ""
        # self.Tmp.current_obj = index
        # self.Tmp.current_obj_name = region.tag(
        #    f'name:{self.Tmp.objects_language}')
        if self.Tmp.search_locations:
            for choice in self.Tmp.search_places_choice:
                points_search_line = f"{points_search_line} "\
                    f"nwr[place='{choice}'](area.a1);"
            base_req_line = f"area({region.areaId()})->.a1; "\
                f"({points_search_line});out body;"
        points = self.overpass.query(base_req_line, timeout=60)
        self.Tmp.sub_obj_number = len(points.nodes())
        for i, p in enumerate(points.nodes()):
            print(p.lon(), p.lat())
            n = self.nominatim.query(
                f"{p.type()}/{p.id()}", zoom=10, lookup=True,
                params={'accept-language': f'{self.Tmp.objects_language}'})
            adr = n.address()
            print(adr)
            adr_mod = {}
            for x in keys_list:
                try:
                    loc = adr[x]
                    if x in self.Tmp.search_places_choice:
                        adr_mod["location"] = loc

                    else:
                        adr_mod[x] = loc
                except Exception:
                    continue
            adr_mod["lon"] = p.lon()
            adr_mod["lat"] = p.lat()
            try:
                kml_doc.newpoint(
                    name=adr_mod["location"], coords=[(p.lon(), p.lat())])
            except KeyError:
                print("No location name - Skip")
                print("------------------")
                continue
            print(adr_mod["location"])
            self.Tmp.current_obj = i
            self.Tmp.current_sub_obj_name = adr_mod["location"]  # ! Too late
            dict_list.append(adr_mod)
            print("------------------")
        if self.Tmp.export_to_excel:
            df = pd.DataFrame(
                dict_list, columns=["location", "county", "state", "region",
                                    "country", "lon", "lat"])
            df.to_excel(self.excel_writer,
                        sheet_name=f"{self.Tmp.current_area_obj_name}")
            print(df)

    def first_nominatim_search(self, single_obj_req: tuple[str, int]) -> str:
        """
        Searches object with Nominatim in chosen (in Tmp parameters)
        mode: World, Country or State to retrieve its id.

        Args:
            single_obj_req (tuple[str, int]):
                Tuple with object name and administrative level

        Returns:
            str: Nominatim id
        """
        self.kml_doc = simplekml.Kml()
        if self.Tmp.search_type == "world" or self.Tmp.search_type == "":
            osm_data = self.nominatim.query(
                single_obj_req[0], params={'accept-language':
                                           f'{self.Tmp.objects_language}'})
            # language=self.Tmp.objects_language
        else:
            osm_data = self.nominatim.query(
                "", params={'accept-language': f'{self.Tmp.objects_language}',
                            f'{self.Tmp.search_type}': f'{single_obj_req[0]}'})
        print(dir(osm_data))
        print(osm_data.address())  # displayName())
        print(osm_data._queryString)

        search_mode = 0
        if search_mode == 0:
            js = osm_data.toJSON()
            for res in js:
                print(res)
                # print(len(js))
            self.Tmp.current_search_json = js
        return f"{js[0]['osm_type'][0]}{js[0]['osm_id']}"

    def overpass_search(self, area_id: str,
                        single_obj_req: tuple[str, int]) -> OverpassResult:
        """
        Tries different admin levels from 'admin_level_try_list' and returns
        first correct Overpass result.

        Args:
            area_id (str):
                Nominatim id from 'first_nominatim_search' result
            single_obj_req (tuple[str, int]):
                Tuple with object name and administrative level

        Returns:
            OverpassResult: Found Overpass regions
        """
        regions = self.overpass.query

        admin_level_try_list = self.admin_level_try_list_creator(
            single_obj_req[1], [4, 5, 6, 7, 8, 9, 10, 3])  # [3,4,5,6,7,8,9,10]

        for i in admin_level_try_list:
            try:
                query = overpassQueryBuilder(
                    area=area_id, elementType='relation',
                    selector=['"boundary"="administrative"',
                              f'"admin_level"="{i}"'], out='body')
                # f"area({osm_data.areaId()})->.searchArea;
                # (relation["boundary"="administrative"]["admin_level"="4"]
                # (area.searchArea);); out body";
                regions = self.overpass.query(query)
                self.Tmp.sub_obj_number = len(regions.relations())
                self.Tmp.current_area_obj_number = self.Tmp.sub_obj_number
                print(query)
                break
            except TypeError:
                self.Tmp.logger_object.warning(
                    f"No administrative level {i} found")
                continue
        return regions

    def second_nominatim_search(self,
                                overpass_regions: OverpassResult) -> None:
        """
        Second Nominatim search, which using Overpass results to create
        borders and points.

        Args:
            overpass_regions (OverpassResult): Overpass regions to proccess
        """
        try:
            if self.Tmp.search_locations and self.Tmp.export_to_excel:
                self.excel_writer = pd.ExcelWriter(
                    f".\\exports\\{self.Tmp.current_obj_name}.xlsx",
                    engine="xlsxwriter")
            for i, region in enumerate(overpass_regions.relations()):
                if self.Tmp.search_borders and self.Tmp.search_locations:
                    cur_folder = self.kml_doc.newfolder(
                        name=self.choose_name_from_tag(region.tags()))
                else:
                    cur_folder = self.kml_doc

                if self.Tmp.search_borders:
                    self.regions_search(i, region, cur_folder)
                if self.Tmp.search_locations:
                    self.locations_search(i, region, cur_folder)
                self.Tmp.current_stage_num = 0
        except TypeError:
            self.Tmp.logger_object.error(
                    "No administrative levels found")
            self.Tmp.current_stage_num = 0
            self.Tmp.error_found = 1

    def request_and_proccess_data(self) -> None:
        """Gathers all 3 searches together and exports configured data.
        """
        search_list = self.search_line_proccessing()
        for single_obj_req in search_list:
            osm_area_id = self.first_nominatim_search(single_obj_req)
            overp_regions = self.overpass_search(osm_area_id, single_obj_req)
            self.second_nominatim_search(overp_regions)
            if self.Tmp.error_found == 0:
                if self.Tmp.export_to_excel:
                    self.save_excel(single_obj_req[0])
                if self.Tmp.export_to_kml:
                    self.save_kml(single_obj_req[0])
            else:
                self.Tmp.error_found = 0


def script_sequence() -> None:
    """Script running without GUI.
    """
    Tmp = TempData()
    try:
        Converter = EarthCrawler(Tmp)
        Converter.request_and_proccess_data()
    except Exception:
        Tmp.logger_object.exception("UncaughtException")
        Tmp.logger_object.warning("Ending script due too uncaught exception")


if __name__ == "__main__":
    script_sequence()
