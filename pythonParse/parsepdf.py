# -*- coding: utf-8 -*-
"""
Ce script analyse une page d'une partition en notation "Tonic Solfa" depuis un fichier PDF.
Il sépare les lignes de notes des lignes de paroles, identifie jusqu'à 4 voix,
et génère un fichier JSON structuré, préformaté pour une conversion en MusicXML.

Ce script a été mis à jour pour :
1.  Créer un DataFrame pandas avec les coordonnées et le texte de chaque élément.
2.  Classifier chaque ligne comme 'notes' ou 'lyrics'.
3.  Colorer les lignes qui sont à moins de 5 pixels les unes des autres.
4.  Générer un fichier HTML pour visualiser le DataFrame avec un style dynamique, incluant
    le décalage des symboles et des flèches pour lier les notes.
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

# --- Fonctions pour le traitement et l'analyse ---

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
    Sépare les notes et les symboles de temps/octave si elles sont dans la même chaîne de texte.
    Les types de textes sont : 'note', 'rhythm', 'octave', 'continuation', 'lyric'.
    """
    print("Classification et annotation des textes...")
    new_data = []
    
    note_id_counter = 0
    rhythm_id_counter = 0
    octave_id_counter = 0
    continuation_id_counter = 0

    # Définition des expressions régulières pour la décomposition
    # Les expressions sont dans l'ordre de priorité (notes, octaves, rythmes, continuation)
    note_regex = r'[drmfslt]'
    octave_regex = r'│'
    rhythm_regex = r'[\:\.\,\|]'
    continuation_regex = r'-'

    combined_regex = f"({octave_regex}|{note_regex}|{rhythm_regex}|{continuation_regex})"
    
    for _, row in df.iterrows():
        text_to_process = row['text'].strip()
        
        # S'assurer que le texte ne contient que des espaces s'il n'y a rien d'autre
        if not text_to_process:
            continue

        # Utiliser re.split pour découper la chaîne en gardant les délimiteurs
        # Ce n'est pas aussi simple car il faut aussi gérer les mots restants.
        # Une approche manuelle est plus fiable.
        
        matches = list(re.finditer(combined_regex, text_to_process, re.IGNORECASE))
        
        if not matches:
            # Si aucun symbole ou note n'est trouvé, le texte est une parole
            new_data.append({
                'text': text_to_process,
                'x': row['x'],
                'y': row['y'],
                'type': 'lyric',
                'id': ''
            })
        else:
            last_pos = 0
            for match in matches:
                # Gérer le texte qui précède le match (s'il existe)
                preceding_text = text_to_process[last_pos:match.start()].strip()
                if preceding_text:
                    new_data.append({
                        'text': preceding_text,
                        'x': row['x'],
                        'y': row['y'],
                        'type': 'lyric',
                        'id': ''
                    })
                
                # Gérer le texte du match lui-même
                matched_text = match.group(0)
                
                if re.search(octave_regex, matched_text):
                    octave_id_counter += 1
                    new_data.append({
                        'text': matched_text,
                        'x': row['x'],
                        'y': row['y'],
                        'type': 'octave',
                        'id': f"octave_{octave_id_counter}"
                    })
                elif re.search(note_regex, matched_text, re.IGNORECASE):
                    note_id_counter += 1
                    new_data.append({
                        'text': matched_text,
                        'x': row['x'],
                        'y': row['y'],
                        'type': 'note',
                        'id': f"note_{note_id_counter}"
                    })
                elif re.search(rhythm_regex, matched_text):
                    rhythm_id_counter += 1
                    new_data.append({
                        'text': matched_text,
                        'x': row['x'],
                        'y': row['y'],
                        'type': 'rhythm',
                        'id': f"rhythm_{rhythm_id_counter}"
                    })
                elif re.search(continuation_regex, matched_text):
                    continuation_id_counter += 1
                    new_data.append({
                        'text': matched_text,
                        'x': row['x'],
                        'y': row['y'],
                        'type': 'continuation',
                        'id': f"continuation_{continuation_id_counter}"
                    })
                
                last_pos = match.end()

            # Gérer le texte restant après le dernier match
            remaining_text = text_to_process[last_pos:].strip()
            if remaining_text:
                new_data.append({
                    'text': remaining_text,
                    'x': row['x'],
                    'y': row['y'],
                    'type': 'lyric',
                    'id': ''
                })

    df_final = pd.DataFrame(new_data)
    print("Classification terminée.")
    return df_final

def associate_symbols_to_notes(df: pd.DataFrame) -> pd.DataFrame:
    """
    Associe les symboles de rythme et de continuation aux notes précédentes.
    """
    print("Association des symboles aux notes...")
    df = df.copy()
    df['associated_id'] = None
    note_ids = df[df['type'] == 'note']['id'].tolist()
    
    for index, row in df.iterrows():
        if row['type'] in ['rhythm', 'continuation', 'octave']:
            # Trouver la note la plus proche (à gauche) dans la même ligne
            line_notes = df[(df['y'] == row['y']) & (df['x'] < row['x']) & (df['type'] == 'note')]
            if not line_notes.empty:
                # La note la plus proche est la dernière note de la ligne avant le symbole
                last_note_id = line_notes.iloc[-1]['id']
                df.loc[index, 'associated_id'] = last_note_id
    
    print("Association terminée.")
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
        #info-box {{ margin-top: 20px; padding: 10px; border: 1px solid #ccc; background-color: #f9f9f9; font-size: 12px; }}
        #info-box h3 {{ margin-top: 0; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Analyse de la partition : {page_title}</h1>
        <canvas id="partitionCanvas"></canvas>
        <div id="info-box">
            <h3>Informations sur les éléments</h3>
            Cliquez sur un symbole (bleu, vert ou gris) pour voir sa note associée.
        </div>
    </div>

    <script>
        const canvas = document.getElementById('partitionCanvas');
        const ctx = canvas.getContext('2d');
        const dfData = {df_json};

        const colors = {{
            'note': 'black',
            'rhythm': 'green',
            'octave': 'blue',
            'continuation': 'gray',
            'lyric': 'red'
        }};

        // Dictionnaire pour stocker les coordonnées des notes par ID
        const notePositions = {{}};

        function drawText() {{
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.font = '10px sans-serif';
            ctx.textAlign = 'left';

            const maxX = Math.max(...dfData.map(item => item.x)) || 0;
            const maxY = Math.max(...dfData.map(item => item.y)) || 0;
            const minX = Math.min(...dfData.map(item => item.x)) || 0;
            const minY = Math.min(...dfData.map(item => item.y)) || 0;

            const padding = 20;
            canvas.width = (maxX - minX) + 2 * padding;
            canvas.height = (maxY - minY) + 2 * padding;

            const xOffset = -minX + padding;
            const yOffset = -minY + padding;

            dfData.forEach(item => {{
                const y_adjusted = canvas.height - (item.y + yOffset);
                
                // Décalage pour les symboles de rythme/continuation
                let x_adjusted = item.x + xOffset;
                if (item.type === 'rhythm' || item.type === 'continuation') {{
                    x_adjusted += 5; // Décalage pour le visuel
                }}
                
                ctx.fillStyle = colors[item.type] || 'black';
                ctx.fillText(item.text, x_adjusted, y_adjusted);
                
                // Stocker la position de chaque note
                if (item.type === 'note') {{
                    notePositions[item.id] = {{x: x_adjusted, y: y_adjusted}};
                }}
            }});
            
            // Dessiner les flèches après avoir dessiné le texte
            dfData.forEach(item => {{
                if (item.type === 'rhythm' || item.type === 'continuation' || item.type === 'octave') {{
                    const associatedNotePos = notePositions[item.associated_id];
                    if (associatedNotePos) {{
                        const startX = item.x + xOffset + (item.text.length * 5); // Décalage + une estimation de la largeur du texte
                        const startY = canvas.height - (item.y + yOffset);
                        
                        // Dessiner une simple flèche de texte pour la visualisation
                        ctx.fillStyle = 'blue';
                        ctx.fillText('→', startX, startY);
                    }}
                }}
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
            "id": row['id'],
            "associated_id": row['associated_id'] # Ajout du lien
        })
        
    # Classification des lignes
    for y, line_data in lines_dict.items():
        is_notes = any(elem['type'] in ['note', 'rhythm', 'octave', 'continuation'] for elem in line_data['elements'])
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
    
    # 3. Association des symboles aux notes
    df_final = associate_symbols_to_notes(df_classified)

    # 4. Génération des fichiers de sortie
    generate_html_from_dataframe(df_final, pdf_title)
    generate_json_from_dataframe(df_final, pdf_title)

if __name__ == "__main__":
    main()
