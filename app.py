import datetime
import json
import time
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.support.ui import Select # Select
from selenium.webdriver.common.by import By 
from  selenium.webdriver.support.ui  import  WebDriverWait 
from  selenium.webdriver.support  import  expected_conditions  as  EC
import pymysql

# 將整理的區域寫成HASH MAP
def write_Map_JSON():
    regions_path = "./json/regions.json"
    with open(regions_path, 'r', encoding="utf8") as json_file: # 讀取 JSON檔案
        regions_data = json.load(json_file) # regions變數為所有要抓取鄉鎮資訊

    map_regions = dict()
    for region in regions_data:
        city = region['city']
        if city not in map_regions:
            map_regions[city] = list()
        map_regions[city].append(region)
    
    to_path = f"json/map_regions.json"
    json_object = json.dumps(map_regions, indent=4, ensure_ascii=False)
    with open(to_path, "w", encoding="utf8") as outfile:
        outfile.write(json_object)
    
    return json_object


"""立即資訊"""
def getNow(soup):
    C_weather_table = soup.find("table", {"class": "cubeV9-table"})
    tbody = C_weather_table.find("tbody")
    tds = tbody.find_all("td")
    C_Weather = dict()
    for td in tds:
        span = td.find("span")
        class_name = span['class'][0]

        # 這邊因為溫度部分有分 『攝氏溫度』及『華氏溫度』。因此<span>底下還有個<span>
        if( (class_name == 'GT_T') | (class_name == 'GT_AT')):
            C_Weather[class_name] = span.find("span", {"class", "is-active"}).getText()
            continue

        C_Weather[class_name] = span.getText()
    return C_Weather

"""逐三小時預報"""
def getThreeHours(soup):
    three_hours_weather_table = soup.find("table", {"id": "TableId3hr"})
    total = dict()

    #region (處理表頭) => 注意有 colspan問題
    thead = three_hours_weather_table.find("thead")
    ths = thead.find_all("th", {"headers": "PC3_D"})
    for th in ths:
        header_name = th["headers"][0]
        if( header_name not in total ):
            total[header_name] = []
        colspan = th["colspan"] if (th.has_attr("colspan")) else 1 # 判斷該日期跨足了幾個時間區間(如果不存在colaspan代表只有一欄就弄1就好)
        total[header_name].extend( [ th.getText() for i in range(0, int(colspan)) ] ) # 依照跨足時間區間的數量透過一行迴圈來push到陣列中
    
    tbody = three_hours_weather_table.find("tbody")
    trs = tbody.find_all("tr")
    #endregion

    #region (處理表格內容)
    for tr in trs:
        ths = tr.find_all("th", {"headers": "PC3_Ti"}) # 抓到所有<th headers="PC3_Ti"></th>
        for th in ths:
            header_name = th["headers"][0]
            if( header_name not in total ):
                total[header_name] = []
            total[header_name].append(th.getText())

        tds = tr.find_all("td")
        for td in tds:
            header_name = td["headers"][0]
            if(  header_name not in total ): # 當目前Dict中無該key時，立即定義
                total[header_name] = []

            # 天氣說明: 只抓文字說明
            if(header_name == "PC3_Wx"): 
                img = td.find("img")
                total[header_name].append(img['alt'])
                continue

            # 溫度: 底下還有分『攝氏溫度』及『華氏溫度』
            if( (header_name == 'PC3_T') | (header_name == 'PC3_AT') ): 
                temp = td.find("span", {"class", "is-active"}).getText()
                total[header_name].append(temp)
                continue

            # 降雨機率: 因為降雨機率這邊會以兩個區間為一個值
            if(header_name == "PC3_Po"): 
                if( td.has_attr('colspan') ): # 如果該欄為兩欄式則要一次push兩筆
                    total[header_name].extend( [td.getText(), td.getText()] ) 
                    continue

            total[header_name].append(td.getText())
    #endregion

    # print(total)
    result = list()
    keys = total.keys()
    for index in range(0, len(total["PC3_Ti"])): # 開始抓取各時間點的預測數據
        list_key = list() # 用來記錄單一時間點的所有天氣數據
        for key in keys: # 透過keys去做不同數據的切換
            list_key.append( total[key][index] )
        zip_dict = dict( zip(keys, list_key) ) # 透過zip將兩個List轉換成dict。
        result.append(zip_dict)
    return result

"""一週預報(寫法跟逐三小時預報差不多)"""
def getSevenDays(soup):
    table = soup.find("table", {"id": "TableIdweeks"})
    total = dict()

    #region (處理表頭) => 注意有 colspan問題
    thead = table.find("thead")
    D_ths = thead.find_all("th", {"headers": "PC7_D"})
    for th in D_ths:
        header_name = th["headers"][0]
        if( header_name not in total ):
            total[header_name] = []
        colspan = th["colspan"] if (th.has_attr("colspan")) else 1 # 判斷該日期跨足了幾個時間區間(如果不存在colaspan代表只有一欄就弄1就好)
        date = th.getText()
        date = date.split("星")[0] # 這邊因為抓到的資料會是  "<XX/XX>星期X"。我只需要前面的日期而已
        date = datetime.datetime.strptime( f"{ datetime.date.today().year }/{date}", "%Y/%m/%d")
        date = datetime.datetime.strftime( date, "%Y-%m-%d" )
        total[header_name].extend( [ date for i in range(0, int(colspan)) ] ) # 依照跨足時間區間的數量透過一行迴圈來push到陣列中
    #endregion

    #region (處理表格內容)
    tbody = table.find("tbody")
    trs = tbody.find_all("tr")
    for tr in trs:
        ths = tr.find_all("th", {"headers": "PC7_Ti"}) # 抓到所有<th headers="PC7_Ti"></th>
        for th in ths:
            header_name = th["headers"][0]
            if( header_name not in total ):
                total[header_name] = []
            total[header_name].append(th.getText())

        tds = tr.find_all("td")
        for td in tds:
            header_name = td["headers"][0]
            if(  header_name not in total ): # 當目前Dict中無該key時，立即定義
                total[header_name] = []
            if(header_name == "PC7_Wx"): # 天氣說明只抓文字說明
                img = td.find("img")
                total[header_name].append(img['alt'])

                continue
            if( (header_name == 'PC7_MaxT') or (header_name == 'PC7_MinT') or (header_name == 'PC7_MaxAT') or (header_name == 'PC7_MinAT')): # 溫度底下還有分『攝氏溫度』及『華氏溫度』
                temp = td.find("span", {"class", "is-active"}).getText()
                total[header_name].append(temp)
                continue
            
            if(header_name == "PC7_UVI"):
                uvi = td.find("span").getText()
                total[header_name].extend( [uvi, uvi] )
                continue

            total[header_name].append(td.getText())
    #endregion


    result = list()
    keys = total.keys()
    for index in range(0, len(total["PC7_D"])): # 開始抓取各時間點的預測數據
        list_key = list() # 用來記錄單一時間點的所有天氣數據
        for key in keys: # 透過keys去做不同數據的切換
            list_key.append( total[key][index] )
        zip_dict = dict( zip(keys, list_key) ) # 透過zip將兩個List轉換成dict。
        result.append(zip_dict)

    return result

# 連線
def connect_db(host, user, pwd, dbname, port):
    try:
        db = pymysql.connect(
            host = host,
            user = user,
            passwd = pwd,
            database = dbname,
            port = int(port)
        )
        # print("連線成功")
        return db
    except Exception as e:
        print('連線資料庫失敗: {}'.format(str(e)))
    return None

# 爬蟲
def Crawler(url, regions):
    try:
    #region (chromedriver 設定)
        option = webdriver.ChromeOptions() # ChromeDriver Options
        # 【參考】https://ithelp.ithome.com.tw/articles/10244446
        option.add_argument("headless") # 不開網頁搜尋
        option.add_argument('blink-settings=imagesEnabled=false') # 不加載圖片提高效率
        option.add_argument('--log-level=3') # 這個option可以讓你跟headless時網頁端的console.log說掰掰
        """下面參數能提升爬蟲穩定性"""
        option.add_argument('--disable-dev-shm-usage') # 使用共享內存RAM
        option.add_argument('--disable-gpu') # 規避部分chrome gpu bug

        driver = webdriver.Chrome(chromedriver_path, chrome_options=option) #啟動模擬瀏覽器
    #endregion

    #region (啟動 chromedriver)
        print("=======================================")
        print(f"💖【{city}】 ({count}/{len(map_regions)})")

        driver.get(url) #取得網頁代碼
        # if not driver.title:
        #     print(f"📛未成功進入頁面...")
        #     pass
            
        # print(f"✅成功進入頁面...({driver.title})")
    #endregion

    #region (選單處理 + 切換近三小時 / 一周)
        # 縣市選單
        select_County = WebDriverWait(driver, 10, 1).until(
            EC.presence_of_element_located(
                (By.XPATH, '//*[@id="CountySelect"]')
            )
        )
        select_County = Select( select_County )
        
        # 區域選單
        select_TID = WebDriverWait(driver, 10, 1).until(
            EC.presence_of_element_located(
                (By.XPATH, '//*[@id="TID"]')
            )
        )
        select_TID = Select( select_TID )


        # 【切換 近三小時預測 / 一周預測】
        three_hours_aTag = driver.find_element(By.XPATH, '//*[@id="Tab_3hrTable"]')
        one_week_aTag = driver.find_element(By.XPATH, '//*[@id="Tab_weeksTable"]')

        one_week_aTag.click() # 切換到一周
    #endregion

        # 開始切換鄉鎮區
        for i, region in enumerate(regions):
        # for i, region in enumerate(regions[0:1]):
            print("-----")
            print(f"目前進度: {region['city'] + region['district']}({i+1}/{len(regions)})")
            # 得到當前區域天氣
            select_TID.select_by_value(region["ID"])

            # 透過 soup解析 XML
            soup = BeautifulSoup(driver.page_source, "lxml")

            #region (即時資訊)
            try:
                # 確定有這個資料再開始抓
                GT_Time = WebDriverWait(driver, 10, 1).until(
                    EC.presence_of_element_located(
                        (By.CLASS_NAME, 'GT_Time')
                    )
                )
                now_info = getNow(soup) 
                # print(f"溫度: {now_info['GT_T']} ； 濕度: {now_info['GT_RH']}")
                now_info = json.dumps(now_info, indent = 4)
            except Exception as e:
                print(f"{region['city']}{region['district']}抓取即時資訊時發生問題 : {e}")
                continue
            #endregion

            

            #region (逐三小時預報)
            try:
                # 確定有這個資料再開始抓
                TableId3hr = WebDriverWait(driver, 10, 1).until(
                    EC.presence_of_element_located(
                        (By.ID, 'TableId3hr')
                    )
                )
                three_hours = getThreeHours(soup) 
                three_hours = json.dumps(three_hours, indent = 4)
            except Exception as e:
                print(f"{region['city']}{region['district']}抓取逐三小時預報時發生問題 : {e}")
                continue
            finally:
                one_week_aTag.click() # 切換到一周
            #endregion

            

            #region (一週預報)
            try:
                # 確定有這個資料再開始抓
                TableIdweeks = WebDriverWait(driver, 10, 1).until(
                    EC.presence_of_element_located(
                        (By.ID, 'TableIdweeks')
                    )
                )
                seven_days = getSevenDays(soup) 
                seven_days = json.dumps(seven_days, indent = 4)
            except Exception as e:
                print(f"{region['city']}{region['district']}抓取一週預報時發生問題 : {e}")
                continue
            finally:
                three_hours_aTag.click() # 切換到逐三小時預報
            #endregion

            #region (資料庫寫入)
            with db.cursor() as cursor: # 資料處理好後，進行資料庫新增動作
                cursor.execute(
                    """INSERT INTO `weather_region` 
                        (`id`, `city`, `district`, `now_info`, `threehours`, `sevendays`) 
                        VALUES (%s, %s, %s, %s, %s, %s) 
                    ON DUPLICATE KEY UPDATE now_info = %s, threehours = %s, sevendays = %s""",
                    (
                        region['ID'], region['city'], region['district'], now_info, three_hours, seven_days , 
                        now_info, three_hours, seven_days,
                    )
                )
                db.commit() # 儲存變更
            #endregion
        
    except KeyboardInterrupt:
        print("----(已中斷程式)----")
    
    except Exception as e:
        print(f"發生問題: {e}")

    finally:
        print("----(ChromeDriver已關閉)----")
        driver.close()
        driver.quit()




if __name__ == '__main__':
    final_start = time.time()

    db = connect_db(
        host='127.0.0.1',
        user='root',
        pwd='Ru,6e.4vu4wj/3',
        dbname='greenhouse',
        port=3306,
    ) # 資料庫連線

    if( not db ):
        print("資料庫連線發生問題")
    

    #region (!製作 hash map)
    # json_object = write_Map_JSON()
    # print(json_object)
    #endregion
    # start = time.time() # 紀錄開始時間(最終要得到整個執行過程總共花費多少時間)

    try:
        regions_path = "./json/map_regions.json"
        with open(regions_path, 'r', encoding="utf8") as json_file: # 讀取 JSON檔案
            map_regions = json.load(json_file) # regions變數為所有要抓取鄉鎮資訊

        chromedriver_path = './chromedriver.exe'  # chromedriver
        count = 1
        

        
        # 【單一縣市測試】
        # city = '基隆市'
        # regions = map_regions[city]
        # url = f'https://www.cwb.gov.tw/V8/C/W/Town/Town.html?TID={regions[0]["ID"]}' # 從第一筆開始抓
        # Crawler(url, regions)
        # print(f"【爬蟲】總花費時間: {format( time.time() - start)}秒")

        # 【全縣市測試】
        for city, regions in map_regions.items():
            url = f'https://www.cwb.gov.tw/V8/C/W/Town/Town.html?TID={regions[0]["ID"]}' # 從第一筆開始抓
            Crawler(url, regions)
            count +=1
    
    except Exception as e:
        pass
    
    finally:
        
        
        print(f"程式已經執行完畢，總花費時間: {format( time.time() - final_start)}秒")
        print("視窗將在兩秒後將關閉...")
        time.sleep(2)
    

