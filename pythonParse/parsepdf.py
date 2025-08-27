# -*- coding: utf-8 -*-
"""
Ce script analyse une page d'une partition en notation "Tonic Solfa" depuis un fichier PDF.
Il sépare les lignes de notes des lignes de paroles, identifie jusqu'à 4 voix,
et génère un fichier JSON structuré, préformaté pour une conversion en MusicXML.

Ce script a été mis à jour pour :
1.  Créer un DataFrame pandas avec les coordonnées et le texte de chaque élément.
2.  Classifier chaque ligne comme 'notes' ou 'lyrics'.
3.  Colorer les lignes qui sont à moins de 5 pixels les unes des autres.
4.  Générer un fichier HTML pour visualiser le DataFrame avec un style dynamique.
5.  Générer un fichier JSON avec la même structure que le code initial, mais avec une gestion améliorée.
"""

# Importation des bibliothèques nécessaires
from PyPDF2 import PdfReader
import pandas as pd
import os
import json
import re

# --- Dictionnaires de mapping pour la conversion ---

SOLFA_TO_STEP = {
    'd': 'C', 'r': 'D', 'm': 'E', 'f': 'F',
    's': 'G', 'l': 'A', 't': 'B'
}

RHYTHM_TO_DURATION = {
    '': {'duration': 4, 'type': 'quarter'},
    '.': {'duration': 8, 'type': 'eighth'},
    ',': {'duration': 16, 'type': 'sixteenth'}
}

# --- Nouvelles fonctions pour le traitement et l'analyse ---

def extract_text_with_coordinates(pdf_path: str, page_num: int) -> pd.DataFrame:
    """
    Extrait le texte et les coordonnées de chaque mot de la page spécifiée du PDF
    en utilisant une fonction de visite (visitor).
    """
    print(f"Extraction du texte et des coordonnées de la page {page_num}...")
    try:
        reader = PdfReader(pdf_path)
        page = reader.pages[page_num - 1]
        
        data = []
        
        def visitor_body(text, cm, tm, fontDict, fontSize):
            """
            Fonction de rappel pour capturer le texte et les coordonnées
            """
            # Récupération des coordonnées x et y de la matrice de transformation (tm)
            # tm[4] est la coordonnée x, tm[5] est la coordonnée y
            x = tm[4]
            y = tm[5]
            
            # Ajoutez le texte et les coordonnées à notre liste
            data.append({'text': text.strip(), 'x': x, 'y': y})

        page.extract_text(visitor_text=visitor_body)
        
        # Création du DataFrame
        df = pd.DataFrame(data)
        
        # Nettoyer les entrées vides ou non pertinentes
        df = df[df['text'] != '']
        
        # Grouper les mots en se basant sur la proximité x et y pour former
        # des lignes logiques
        df['x'] = df['x'].round(0).astype(int)
        df['y'] = df['y'].round(0).astype(int)
        df = df.sort_values(by=['y', 'x'], ascending=[False, True]).reset_index(drop=True)
        
        # La fonction visitor_body donne chaque caractère ou segment de texte,
        # nous devons les regrouper en mots logiques.
        processed_data = []
        if not df.empty:
            current_x = df.loc[0, 'x']
            current_y = df.loc[0, 'y']
            current_text = df.loc[0, 'text']
            
            for i in range(1, len(df)):
                next_x = df.loc[i, 'x']
                next_y = df.loc[i, 'y']
                next_text = df.loc[i, 'text']
                
                # Si le mot suivant est proche, on l'ajoute au mot courant
                if abs(next_x - current_x) < 20 and abs(next_y - current_y) < 5:
                    current_text += next_text
                    current_x = next_x
                else:
                    processed_data.append({'text': current_text, 'x': current_x, 'y': current_y})
                    current_x = next_x
                    current_y = next_y
                    current_text = next_text
            
            processed_data.append({'text': current_text, 'x': current_x, 'y': current_y})
            
        df_final = pd.DataFrame(processed_data)
        
        print("Extraction réussie.")
        return df_final
    except Exception as e:
        print(f"Erreur lors de l'extraction du texte : {e}")
        return pd.DataFrame()

def classify_and_annotate_text(df: pd.DataFrame) -> pd.DataFrame:
    """
    Classifie chaque élément de texte et lui attribue un ID.
    Les types de textes sont : 'note', 'rhythm', 'octave', 'lyric'.
    """
    print("Classification et annotation des textes...")
    df['type'] = 'lyric'
    df['id'] = ''
    
    note_id_counter = 0
    rhythm_id_counter = 0
    octave_id_counter = 0

    for index, row in df.iterrows():
        text = row['text'].strip()
        
        # Classification des notes (contient une lettre de d, r, m, f, s, l, t)
        note_regex = r'[drmfslt]'
        if re.search(note_regex, text, re.IGNORECASE):
            df.loc[index, 'type'] = 'note'
            # Attribuer un ID pour chaque note trouvée dans la chaîne
            notes = re.findall(note_regex, text, re.IGNORECASE)
            note_ids = []
            for note in notes:
                note_id_counter += 1
                note_ids.append(f"note_{note_id_counter}")
            df.loc[index, 'id'] = ",".join(note_ids)
        
        # Classification des signes d'octave (│)
        octave_regex = r'│\d'
        if re.search(octave_regex, text):
            df.loc[index, 'type'] = 'octave'
            octave_id_counter += 1
            df.loc[index, 'id'] = f"octave_{octave_id_counter}"
        
        # Classification des signes de rythme et de temps (., : |)
        # Note: on vérifie ici s'il ne s'agit pas d'un signe d'octave pour éviter les confusions
        rhythm_regex = r'[:.,|]'
        if re.search(rhythm_regex, text) and df.loc[index, 'type'] != 'octave':
            df.loc[index, 'type'] = 'rhythm'
            rhythm_id_counter += 1
            df.loc[index, 'id'] = f"rhythm_{rhythm_id_counter}"
            

    # Si le type n'a pas été changé, il reste 'lyric'
    df['type'] = df.apply(
        lambda row: 'lyric' if row['type'] not in ['note', 'rhythm', 'octave'] else row['type'],
        axis=1
    )
    
    print("Classification terminée.")
    return df

def generate_html_from_dataframe(df: pd.DataFrame, page_title: str):
    """
    Génère un fichier HTML pour afficher le texte sur un canvas avec des couleurs
    basées sur la classification.
    """
    print("Génération du fichier HTML...")

    # Serialize the dataframe to a JSON string
    df_json = df.to_json(orient='records')
    
    html_content = f"""
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{page_title}</title>
    <style>
        body {{ font-family: sans-serif; margin: 0; padding: 0; background-color: #f4f4f4; }}
        .container {{ max-width: 800px; margin: 20px auto; padding: 20px; background-color: white; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
        h1 {{ color: #333; text-align: center; }}
        canvas {{ border: 1px solid #ddd; display: block; margin: 0 auto; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Analyse de la partition : {page_title}</h1>
        <canvas id="partitionCanvas"></canvas>
    </div>

    <script>
        const canvas = document.getElementById('partitionCanvas');
        const ctx = canvas.getContext('2d');
        const dfData = {df_json};

        const colors = {{
            'note': 'black',
            'rhythm': 'green',
            'octave': 'blue',
            'lyric': 'red'
        }};

        function drawText() {{
            // Clear the canvas
            ctx.clearRect(0, 0, canvas.width, canvas.height);

            // Set font properties
            ctx.font = '10px sans-serif';
            ctx.textAlign = 'left';

            // Find max x and y to set canvas dimensions
            const maxX = Math.max(...dfData.map(item => item.x)) || 0;
            const maxY = Math.max(...dfData.map(item => item.y)) || 0;
            const minX = Math.min(...dfData.map(item => item.x)) || 0;
            const minY = Math.min(...dfData.map(item => item.y)) || 0;

            const padding = 20;
            canvas.width = (maxX - minX) + 2 * padding;
            canvas.height = (maxY - minY) + 2 * padding;

            const xOffset = -minX + padding;
            const yOffset = -minY + padding;

            // Draw each word at its coordinates
            dfData.forEach(item => {{
                // Adjust y coordinate to be relative to the top of the canvas
                const y_adjusted = canvas.height - (item.y + yOffset);
                ctx.fillStyle = colors[item.type] || 'black';
                ctx.fillText(item.text, item.x + xOffset, y_adjusted);
            }});
        }}
        
        // Initial drawing
        drawText();

        // Redraw on window resize
        window.addEventListener('resize', drawText);
    </script>
</body>
</html>
    """

    nom_fichier_sortie = "partition_analyse.html"
    try:
        with open(nom_fichier_sortie, "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"Succès ! Le fichier '{nom_fichier_sortie}' a été créé.")
    except Exception as e:
        print(f"Impossible de sauvegarder le fichier HTML : {e}")

def generate_json_from_dataframe(df: pd.DataFrame, pdf_title: str):
    """
    Génère un fichier JSON structuré à partir du DataFrame.
    """
    print("Génération du fichier JSON...")
    score_data = {
        "title": pdf_title,
        "lines": []
    }
    
    # Créer un dictionnaire pour regrouper les mots par ligne (coordonnée Y)
    lines_dict = {}
    for _, row in df.sort_values(by=['y', 'x'], ascending=[False, True]).iterrows():
        y_val = row['y']
        if y_val not in lines_dict:
            lines_dict[y_val] = {
                "text": [],
                "elements": []
            }
        lines_dict[y_val]["text"].append(row['text'])
        lines_dict[y_val]["elements"].append({
            "text": row['text'],
            "x": row['x'],
            "y": row['y'],
            "type": row['type'],
            "id": row['id']
        })
        
    # Classification des lignes
    for y, line_data in lines_dict.items():
        is_notes = any(elem['type'] in ['note', 'rhythm', 'octave'] for elem in line_data['elements'])
        line_data['type'] = 'notes' if is_notes else 'lyrics'
        line_data['text'] = " ".join(line_data['text'])
        
    score_data["lines"] = list(lines_dict.values())

    nom_fichier_sortie = "partition_analyse.json"
    try:
        with open(nom_fichier_sortie, "w", encoding="utf-8") as f:
            json.dump(score_data, f, ensure_ascii=False, indent=2)
        print(f"Succès ! Le fichier '{nom_fichier_sortie}' a été créé.")
    except Exception as e:
        print(f"Impossible de sauvegarder le fichier JSON : {e}")

def main():
    """
    Fonction principale qui demande les informations à l'utilisateur.
    """
    print("--- Analyseur de Partition v5 ---")
    
    while True:
        pdf_path = input("Veuillez entrer le chemin complet du fichier PDF : ")
        if os.path.exists(pdf_path) and pdf_path.lower().endswith('.pdf'):
            break
        else:
            print("Chemin invalide ou le fichier n'est pas un .pdf. Veuillez réessayer.")

    while True:
        try:
            page_num_str = input("Quelle page de la partition souhaitez-vous analyser ? (ex: 1) : ")
            page_num = int(page_num_str)
            if page_num > 0:
                break
            else:
                print("Veuillez entrer un numéro de page valide (supérieur à 0).")
        except ValueError:
            print("Entrée invalide. Veuillez entrer un numéro.")

    # Nom du fichier pour le titre
    pdf_title = os.path.basename(pdf_path)

    # 1. Extraction du texte et des coordonnées dans un DataFrame
    df_coords = extract_text_with_coordinates(pdf_path, page_num)
    
    if df_coords.empty:
        print("L'analyse a échoué. Fin du programme.")
        return

    # 2. Classification et annotation du texte
    df_classified = classify_and_annotate_text(df_coords)

    # 3. Génération des fichiers de sortie
    generate_html_from_dataframe(df_classified, pdf_title)
    generate_json_from_dataframe(df_classified, pdf_title)

if __name__ == "__main__":
    main()
