import pandas as pd
from dotenv import load_dotenv
import streamlit as st
import os
import requests
import mysql.connector
from langchain.schema import AIMessage, HumanMessage

# Cargar variables de entorno
load_dotenv()

# Obtener la clave de la API de Groq
groq_api_key = os.getenv("GROQ_API_KEY")

# URL de la API de Groq
groq_url = "https://api.groq.com/openai/v1/chat/completions"

# Función para inicializar la conexión a la base de datos
def init_database(host, user, password, database, port):
    try:
        connection = mysql.connector.connect(
            host=host,
            user=user,
            password=password,
            database=database,
            port=port,
        )
        return connection
    except mysql.connector.Error as e:
        st.error(f"Error al conectar con la base de datos: {e}")
        return None

# Función para procesar la respuesta de Groq y extraer solo la consulta SQL
def process_groq_response(response):
    try:
        # Revisamos si la respuesta contiene el campo esperado
        content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        print("Contenido original de Groq:", content)  # Para debug, ver todo el contenido de la respuesta

        # Filtramos solo la consulta SQL
        sql_query = ""
        if "SELECT" in content:  # Aseguramos que la respuesta contiene una consulta SQL
            # Encontramos donde comienza la consulta SQL (SELECT, INSERT, etc.)
            start_index = content.find("SELECT")  # Podrías añadir más palabras clave como "INSERT", "UPDATE"
            sql_query = content[start_index:].strip()

            # Buscamos el punto y coma al final de la consulta SQL
            semicolon_index = sql_query.find(';')
            if semicolon_index != -1:
                sql_query = sql_query[:semicolon_index + 1]  # Aseguramos que incluya el punto y coma final
            print("Consulta SQL extraída:", sql_query)  # Para debug, ver la consulta SQL extraída

        # Si no se encontró una consulta SQL, mostramos un error
        if not sql_query:
            st.error("No se encontró una consulta SQL válida en la respuesta de Groq.")
            return None

        return sql_query
    except Exception as e:
        # Si ocurre un error en el procesamiento, mostramos el error
        st.error(f"Error al procesar la respuesta de Groq: {e}")
        return None

# Función para consultar a Groq y generar una consulta SQL
def query_groq(user_message: str, schema: str, chat_history: list):
    headers = {
        "Authorization": f"Bearer {groq_api_key}",
        "Content-Type": "application/json",
    }
    chat_history_text = "\n".join(
        [
            f"{'Usuario' if isinstance(msg, HumanMessage) else 'IA'}: {msg.content}"
            for msg in chat_history
        ]
    )
    data = {
        "model": "llama3-8b-8192",
        "messages": [
            {
                "role": "user",
                "content": f"""
                Eres un analista de datos en una empresa. Basado en el esquema a continuación y el historial de la conversación, 
                por favor genera una consulta SQL y proporciona una respuesta.

                ESQUEMA:
                {schema}

                Historial de Conversación:
                {chat_history_text}

                Pregunta del Usuario: {user_message}
                """,
            }
        ],
    }
    try:
        response = requests.post(groq_url, json=data, headers=headers)
        response.raise_for_status()
        result = response.json()

        # Mostrar toda la respuesta de Groq
        full_response = result["choices"][0]["message"]["content"].strip()
        print("Respuesta completa de Groq:", full_response)  # Para debug, ver la respuesta completa

        # Filtrar solo la consulta SQL de la respuesta
        sql_query = process_groq_response(result)  # Llamar a la función de procesamiento
        return full_response, sql_query
    except requests.exceptions.RequestException as e:
        return f"Error al consultar a Groq: {e}", None

# Función para ejecutar consultas SQL en la base de datos
def execute_query(connection, query):
    try:
        cursor = connection.cursor()
        cursor.execute(query)
        results = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        return pd.DataFrame(results, columns=columns)
    except mysql.connector.Error as e:
        return f"Error al ejecutar la consulta SQL: {e}"
    except Exception as e:
        return f"Error inesperado: {e}"

# Configuración inicial de Streamlit
st.set_page_config(page_title="Chat con MySQL", page_icon=":speech_balloon:")
st.title("Chat con MySQL (Integrado con Groq)")

# Configuración y carga inicial del historial de chat
if "chat_history" not in st.session_state:
    st.session_state.chat_history = [
        AIMessage(content="¡Hola! Soy tu asistente SQL. Pregúntame cualquier cosa sobre tu base de datos."),
    ]

# Barra lateral para configuración de la base de datos
with st.sidebar:
    st.subheader("Configuración de la base de datos")
    host = st.text_input("Host", value="localhost")
    port = st.text_input("Puerto", value="3306")
    user = st.text_input("Usuario", value="root")
    password = st.text_input("Contraseña", type="password", value="")
    database = st.text_input("Base de datos", value="chat")

    # Botón para conectar a la base de datos
    if st.button("Conectar"):
        with st.spinner("Conectando a la base de datos..."):
            connection = init_database(host, user, password, database, port)
            if connection:
                st.session_state.connection = connection
                st.success("¡Conexión exitosa!")
            else:
                st.error("No se pudo conectar a la base de datos.")

# Mostrar historial del chat
for message in st.session_state.chat_history:
    if isinstance(message, AIMessage):
        with st.chat_message("assistant"):
            st.markdown(message.content)
    elif isinstance(message, HumanMessage):
        with st.chat_message("user"):
            st.markdown(message.content)

# Verificar si la conexión se ha realizado
if "connection" in st.session_state and st.session_state.connection:
    connection = st.session_state.connection

    # Obtener el esquema de la base de datos con detalles de las tablas y columnas
    cursor = connection.cursor()
    cursor.execute("SHOW TABLES")
    tables = cursor.fetchall()

    schema = ""
    for table in tables:
        cursor.execute(f"DESCRIBE {table[0]}")
        columns = cursor.fetchall()
        schema += f"\nTabla: {table[0]}\n"
        for column in columns:
            schema += f"  - {column[0]} ({column[1]})\n"

    # Entrada del usuario
    user_query = st.chat_input("Escribe tu mensaje...")
    if user_query:
        # Guardar el mensaje del usuario en el historial
        st.session_state.chat_history.append(HumanMessage(content=user_query))

        # Mostrar el mensaje del usuario
        with st.chat_message("user"):
            st.markdown(user_query)

        # Generar consulta SQL con Groq
        with st.spinner("Generando respuesta con Groq..."):
            full_response, sql_query = query_groq(user_query, schema, st.session_state.chat_history)
            if full_response:  # Si la respuesta completa existe
                st.session_state.chat_history.append(AIMessage(content=full_response))

                # Mostrar toda la respuesta generada por la IA
                with st.chat_message("assistant"):
                    st.markdown(full_response)

                # Ejecutar la consulta en la base de datos si se generó una SQL válida
                if sql_query:
                    result = execute_query(connection, sql_query)
                    if isinstance(result, pd.DataFrame):
                        st.write("Resultados de la consulta:")
                        st.dataframe(result)
                    else:
                        st.error(result)
                else:
                    st.error("No se pudo generar una consulta SQL válida.")
            else:
                st.error("No se pudo obtener una respuesta de Groq.")
else:
    st.warning("Conéctate a una base de datos para empezar.")
