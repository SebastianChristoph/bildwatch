import json
import requests

SHOW_ARTCILE_PRINTS = True
articles = {}
changes_articles = []
JSON_FILE= "bildwatch_plus_article.json"
URL = "https://sebastianchristoph.pythonanywhere.com/bildwatch-api"
last_updated = ""

def open_json():
    global articles
    try:
        print(f"Get JSON from Web {URL}")
        source = requests.get(URL).text
        articles = json.loads(source)
        print("Done.\n")
    except Exception as e:
        print(f"Error loading JSON from Web: {e}")

def analyze_articles(): 
    global articles, last_updated
    count = 0
    found_changes = 0
    if SHOW_ARTCILE_PRINTS: print(f"ID \t\t\t\t Published \t\t Published to Normal \t Title")
    for key, value in articles.items():
        if key == "lastUpdated":
            last_updated = value
            continue
        if SHOW_ARTCILE_PRINTS: print(f"{key} \t {value['published'].split('.')[0]} \t {value['timeBetween']} \t\t\t\t {value['title']} ({value['category']})")
        if value["publishedToNormal"] != None:
            found_changes += 1
        count += 1
    
    print(f"\nLast Updated (UTC): {last_updated.split('.')[0]}")
    print(f"Analyzed {count}, found {found_changes} changed articles\n")


open_json()
analyze_articles()