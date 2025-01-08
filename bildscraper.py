from bs4 import BeautifulSoup
import requests
import json
import os
from datetime import datetime
import time


SHOW_PRINTS = False
articles = {}
scraped_articles = []
URL = "https://www.bild.de/"
headers = {'user-agent':'Mozilla/5.0 (iPhone; CPU iPhone OS 12_3_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Instagram 105.0.0.11.118 (iPhone11,8; iOS 12_3_1; en_US; en-US; scale=2.00; 828x1792; 165586599)'}
PRINT_ERRORS = False
JSON_FILE= "bildwatch_plus_article.json"

cwd = os.getcwd()

def datetime_converter(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError("Type not serializable")

def check_and_open_json() -> dict:
    global articles
    if SHOW_PRINTS: print("GET JSON FILE")
    if not os.path.exists(JSON_FILE):
        if SHOW_PRINTS: print(f"JSON FILE {JSON_FILE} does not exist")

        with open(JSON_FILE, "w", encoding="UTF-8") as json_file:
            json.dump({}, json_file, indent=4)
            print(f"JSON FILE {JSON_FILE} created!")

    with open(JSON_FILE, "r", encoding="UTF-8") as json_file:
        articles = json.load(json_file)

def get_all_articles():
    global articles, scraped_articles
    scraped_articles = []
    source = requests.get(URL, headers = headers).text
    soup = BeautifulSoup(source, "html.parser")
    script_tag = soup.find("script", {"id": "vike_pageContext"})

    if script_tag:
        json_content = script_tag.string.strip()
        try:
            data_dict = json.loads(json_content)

            count = 0
            for article in data_dict["CLIENT_STORE_INITIAL_STATE"]["pageAggregation"]["curation"]["page"]["blocks"]:

                if len(article["layouts"]) > 0:
                    try:
                        article_data = article["layouts"][0]["placements"][0]
                        hasTeaser = article_data.get("teaser")

                        if hasTeaser != None:
                            data = article_data["teaser"]["document"]
                        else:
                            data = article_data["document"]

                        identifier = data.get("id")
                        bildplus = data.get("isPremium")
                        title = data.get("title")
                        url = data.get("canonicalPath")

                        category = None
                        try:
                            relative_path = data.get("relativePath")
                            if relative_path != None:
                                category = relative_path.split("/")[1].capitalize()
                        except:
                            pass

                        if id != None and bildplus != None and url != None:
                            scraped_articles.append(
                                {
                                "identifier" : identifier,
                                "category" : category,
                                "bildplus" : bildplus,
                                "title" : title,
                                "url" : url}
                                )
                        count += 1
                    except Exception as e:
                        if SHOW_PRINTS:
                            print("Error:", e)
                            print(article)
                            print("\n\n")
                else:
                    continue

        except json.JSONDecodeError as e:
            print(f"Fehler beim Parsen des JSON-Inhalts: {e}")
    else:
        print("Script-Tag mit der ID 'vike_pageContext' wurde nicht gefunden.")

def get_article_from_json(scraped_article):
        global articles
        try:
            article_in_json = articles.get(scraped_article["identifier"])
            return article_in_json
        except Exception as e:
            print("Fehler beim JSON GET:", e)
            return None

def post_plus_article(scraped_article):
    #print(f"[NEW] POST PLUS ARTIKEL {scraped_article['identifier']} to JSON {JSON_FILE}")
    now = datetime.now()
    articles[scraped_article['identifier']] = {
        "title" : scraped_article["title"],
        "url" : scraped_article["url"],
        "category" : scraped_article["category"],
        "published" : now,
        "publishedToNormal" : None,
        "timeBetween" : None
    }

def update_plus_article_to_normal(identifier):
    print(f"[CHANGE] UPDATE PLUS ARTIKEL {identifier} to NORMAL in JSON {JSON_FILE}\n\n")
    now = datetime.now()

    published_date = articles[identifier]['published']
    # Verwandelt das Veröffentlichungsdatum in ein datetime-Objekt, falls es noch ein ISO-Format-String ist
    if isinstance(published_date, str):
        published_date = datetime.fromisoformat(published_date)
    
    # Zeit, wann es zu einem normalen Artikel wurde
    articles[identifier]['publishedToNormal'] = now

     # Berechne die Zeitdifferenz zwischen 'publishedToNormal' und 'published'
    time_difference = now - published_date

    # Berechne die Zeitdifferenz in Stunden und Minuten
    hours, remainder = divmod(time_difference.total_seconds(), 3600)
    minutes = remainder // 60

    # Speichere die Zeitdifferenz in 'timeBetween' im Format "X Stunden, Y Minuten"
    articles[identifier]['timeBetween'] = f"{int(hours)}, {int(minutes)}"

def is_bildplus(url):
    source = requests.get(url, headers = headers).text
    index = source.find("isPremium")
    if index:
        info = source[index:index+15]
        if "true" in info:
            return True
    
    return False

def save_to_json():
    global articles
    #print(f"\n\nJSON {JSON_FILE} wird gespeichert")

    # Verwende die Hilfsfunktion, um datetime-Objekte zu serialisieren
    output = json.dumps(articles, indent=4, default=datetime_converter)

    with open(JSON_FILE, "w", encoding="UTF-8") as json_file:
        json_file.write(output)
        print("Erfolgreich gespeichert")

def check_articles():
    global articles

    for scraped_article in scraped_articles:
        found_article = get_article_from_json(scraped_article)
        if found_article != None:
            #print(f"[OLD] PLUS ARTIKEL {scraped_article['identifier']} bereits in JSON {JSON_FILE}")
            # Artikel bereits in DB
            # Check: ist jetzt normaler Artikel?
            if scraped_article["bildplus"] == False:
                update_plus_article_to_normal(scraped_article)
        else:
            # noch nicht in DB
            if scraped_article["bildplus"] == True:
                post_plus_article(scraped_article)
    
    for identifier, value in articles.items():
        if is_bildplus(value["url"]) == False and value["timeBetween"] == None:
            update_plus_article_to_normal(identifier)


if "Desktop" not in cwd:
    while True:
        check_and_open_json()
        get_all_articles()
        check_articles()
        save_to_json()
        time.sleep(5*60)
else:
    check_and_open_json()
    get_all_articles()
    check_articles()
    save_to_json()