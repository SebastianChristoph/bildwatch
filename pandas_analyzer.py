import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
import json
import requests

data = {}

headers = {'user-agent':'Mozilla/5.0 (iPhone; CPU iPhone OS 12_3_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Instagram 105.0.0.11.118 (iPhone11,8; iOS 12_3_1; en_US; en-US; scale=2.00; 828x1792; 165586599)'}
URL = "https://sebastianchristoph.pythonanywhere.com/bildwatch-api"
source = requests.get(URL, headers = headers).text
data = json.loads(source)
data.pop("lastUpdated", None)


# with open('bildwatch_plus_article.json') as json_file:
#     data = json.load(json_file)

def show_publish_data():
    # Data in pandas DataFrame umwandeln
    df = pd.DataFrame.from_dict(data, orient='index')

    # Konvertiere "publishedToNormal" in Datetime und extrahiere nur das Datum
    df['publishedToNormal'] = pd.to_datetime(df['publishedToNormal']).dt.date

    # Entferne Zeilen mit "publishedToNormal" == NaT (fehlende Daten)
    df = df.dropna(subset=['publishedToNormal'])

    # Zählen der Artikel pro Tag
    articles_per_day = df.groupby('publishedToNormal').size()
    articles_per_day_dict = articles_per_day.to_dict()
    unconverted_dict = {}

    for current_date, value in articles_per_day_dict.items():
        unconverted_articles = 0
        current_date = datetime.fromisoformat(str(current_date))

        for article, article_data in data.items():
            published_date = datetime.fromisoformat(article_data["published"])


            if published_date > current_date:
                continue
            
            if article_data["publishedToNormal"] == None:
                unconverted_articles += 1
                continue

            published_to_normal_date = datetime.fromisoformat(article_data["publishedToNormal"])
            
            if published_to_normal_date > current_date:
                unconverted_articles += 1

        unconverted_dict[current_date] = unconverted_articles
 
    test_series = pd.Series(unconverted_dict)
    

        # Erstellen eines Liniendiagramms
    plt.figure(figsize=(12, 6))

   # Linien-Plot für articles_per_day
    articles_per_day.plot(kind='line', marker='o', label="Summe konvertierter Artikel")

    # Flächen-Plot für test_series
    plt.fill_between(test_series.index, test_series.values, color='red', alpha=0.3, label="Summe unkonvertierter Artikel")

    # Diagramm-Einstellungen
    plt.title("Übersicht Verhältnis un/konvertierter BildPlus-Artikel")
    plt.xlabel("Datum")
    plt.ylabel("Anzahl der Artikel")
    plt.xticks(rotation=45)
    plt.legend()
    plt.grid()
    plt.figtext(0.5, 0.95, "Bildrecht und Quelle: sebastianchristoph.com", ha="center", va="center", fontsize=8)


    plt.show()
        

def plot_timebetween_histogram(target_date):

   # Data in pandas DataFrame umwandeln
    df = pd.DataFrame.from_dict(data, orient='index')

    # Konvertiere "publishedToNormal" in Datetime und extrahiere nur das Datum
    df['publishedToNormal'] = pd.to_datetime(df['publishedToNormal']).dt.date

   # Ziel-Datum als datetime.date-Objekt
    target_date = pd.to_datetime(target_date).date()
    
    # Filter für Zeilen, die am Ziel-Datum veröffentlicht wurden
    filtered_df = df[df['publishedToNormal'] == target_date]
    
    # Extrahiere Stunden und Minuten aus "timeBetween" und konvertiere zu Dezimalstunden
    def convert_to_hours(time_str):
        try:
            hours, minutes = map(int, time_str.split(','))
            return hours + minutes / 60  # Umrechnung in Dezimalstunden
        except:
            return None  # Ignorieren, wenn das Format nicht passt
    
    # Wende die Umrechnung an und entferne Zeilen mit None
    filtered_df['hours'] = filtered_df['timeBetween'].dropna().apply(convert_to_hours)

    
    
    # Erstelle das Histogramm der Stunden
    plt.figure(figsize=(10, 6))
    plt.hist(filtered_df['hours'].dropna(), bins=20, edgecolor='black', alpha=0.7)
    plt.title(f"Verteilung der Zeit zwischen Veröffentlichung und Konvertierung am {target_date}")
    plt.xlabel("Anzahl der Stunden zwischen Veröffentlichung als BildPlus-Artikel und Konvertierung")
    plt.ylabel("Anzahl der Artikel")
    plt.xticks(rotation=45)
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    plt.figtext(0.5, 0.95, "Bildrecht und Quelle: sebastianchristoph.com",ha="center", va="center", fontsize=8)
    plt.show()


show_publish_data()

plot_timebetween_histogram("2024-11-18")

    
print("Done")