import streamlit as st
import cv2
import pytesseract
import spacy
import re
import numpy as np
from PIL import Image
import pandas as pd
import json
import sqlite3
from io import BytesIO

# Librerie opzionali
from deep_translator import GoogleTranslator
import smtplib
from email.mime.text import MIMEText
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Carica modello NLP italiano
nlp = spacy.load("it_core_news_sm")

# Funzioni di validazione
def valida_email(email):
    return re.match(r"[^@]+@[^@]+\.[^@]+", email)

def valida_telefono(numero):
    return re.match(r"\+?\d[\d\s\-]{7,}", numero)

# Titolo dell'app
st.title("📇 Estrazione automatica da biglietto da visita")

# Opzioni avanzate
st.sidebar.header("⚙️ Funzionalità extra")
attiva_logo = st.sidebar.checkbox("Rileva logo aziendale")
attiva_traduzione = st.sidebar.checkbox("Traduci in inglese")
attiva_google_sheets = st.sidebar.checkbox("Invia a Google Sheets")
attiva_email = st.sidebar.checkbox("Invia via Email")

# Caricamento immagine
uploaded_file = st.file_uploader("Carica un'immagine del biglietto da visita", type=["jpg", "jpeg", "png"])

if uploaded_file is not None:
    try:
        image = Image.open(uploaded_file)
        st.image(image, caption="Biglietto caricato", use_container_width=True)

        # Conversione in array NumPy per OpenCV
        img_array = np.array(image)

        # 🔍 Logo aziendale
        if attiva_logo:
            logo_crop = img_array[0:100, 0:100]
            logo_image = Image.fromarray(logo_crop)
            st.image(logo_image, caption="🖼️ Logo rilevato (ipotetico)", use_container_width=False)

        # Pre-elaborazione per OCR
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # OCR con Tesseract
        text = pytesseract.image_to_string(thresh, lang='ita')
        st.subheader("📄 Testo estratto")
        st.text(text)

        # Analisi NLP
        doc = nlp(text)
        email = [e for e in re.findall(r"\S+@\S+\.\S+", text) if valida_email(e)]
        telefono = [t for t in re.findall(r"\+?\d[\d\s\-]{7,}", text) if valida_telefono(t)]
        piva = re.findall(r"(?:P\.?IVA\s?:?\s?)?(\d{11})", text)
        nomi = [ent.text for ent in doc.ents if ent.label_ == "PER"]
        aziende = [ent.text for ent in doc.ents if ent.label_ == "ORG"]

        # Output strutturato
        dati = {
            "Ragione Sociale": ", ".join(aziende) if aziende else "Non trovata",
            "Partita IVA": ", ".join(piva) if piva else "Non trovata",
            "Nome Proprietario": ", ".join(nomi) if nomi else "Non trovato",
            "Email": ", ".join(email) if email else "Non trovata",
            "Telefono": ", ".join(telefono) if telefono else "Non trovato"
        }

        st.subheader("📦 Dati estratti")
        for k, v in dati.items():
            st.write(f"**{k}**: {v}")

        # 🌍 Traduzione automatica
        if attiva_traduzione:
            tradotti = {k: GoogleTranslator(source='auto', target='en').translate(v) for k, v in dati.items()}
            st.subheader("🌐 Dati tradotti in inglese")
            for k, v in tradotti.items():
                st.write(f"**{k}**: {v}")

        # Visualizzazione tabellare
        df = pd.DataFrame([dati])
        st.dataframe(df)

        # CSV
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Scarica come CSV", csv, "dati_biglietto.csv", "text/csv")

        # JSON
        json_data = json.dumps(dati, indent=4, ensure_ascii=False).encode('utf-8')
        st.download_button("📥 Scarica come JSON", json_data, "dati_biglietto.json", "application/json")

        # Excel
        excel_buffer = BytesIO()
        df.to_excel(excel_buffer, index=False, engine='openpyxl')
        st.download_button("📥 Scarica come Excel", excel_buffer.getvalue(), "dati_biglietto.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        # Salvataggio in SQLite
        conn = sqlite3.connect("biglietti.db")
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS biglietti (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ragione_sociale TEXT,
            partita_iva TEXT,
            nome_proprietario TEXT,
            email TEXT,
            telefono TEXT
        )
        """)
        cursor.execute("""
        INSERT INTO biglietti (ragione_sociale, partita_iva, nome_proprietario, email, telefono)
        VALUES (?, ?, ?, ?, ?)
        """, (
            dati["Ragione Sociale"],
            dati["Partita IVA"],
            dati["Nome Proprietario"],
            dati["Email"],
            dati["Telefono"]
        ))
        conn.commit()
        conn.close()
        st.success("✅ Dati salvati nel database locale 'biglietti.db'")

        # 📤 Google Sheets
        if attiva_google_sheets:
            try:
                scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
                creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
                client = gspread.authorize(creds)
                sheet = client.open("Biglietti da visita").sheet1
                sheet.append_row(list(dati.values()))
                st.success("📤 Dati inviati a Google Sheets")
            except Exception as e:
                st.error(f"❌ Errore Google Sheets: {e}")

        # 📧 Invio via email
        if attiva_email:
            try:
                msg = MIMEText(json.dumps(dati, indent=4, ensure_ascii=False))
                msg['Subject'] = "Dati biglietto da visita"
                msg['From'] = "tuo@email.it"
                msg['To'] = "destinatario@email.it"

                with smtplib.SMTP('smtp.gmail.com', 587) as server:
                    server.starttls()
                    server.login("tuo@email.it", "tua_password")
                    server.send_message(msg)

                st.success("📧 Email inviata con successo")
            except Exception as e:
                st.error(f"❌ Errore invio email: {e}")

    except Exception as e:
        st.error(f"❌ Errore durante l'elaborazione: {e}")