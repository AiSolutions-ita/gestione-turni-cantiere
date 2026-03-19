import streamlit as st
import pandas as pd
from ortools.sat.python import cp_model
import calendar
from datetime import date
import io
import streamlit_authenticator as stauth 

st.set_page_config(page_title="Gestione Cantiere PRO", layout="wide")

# --- 0. CONFIGURAZIONE AUTENTICAZIONE ---
names = ["Amministratore Cantiere", "Demo Cliente"]
usernames = ["admin", "cliente_demo"]
passwords = ["cantiere2026", "demo123"] 

auth_data = {"usernames": {}}
for i in range(len(usernames)):
    auth_data["usernames"][usernames[i]] = {"name": names[i], "password": passwords[i]}

authenticator = stauth.Authenticate(auth_data, "cookie_cantiere", "key_cantiere", cookie_expiry_days=1)

# --- LOGICA DI ACCESSO ---
authenticator.login(location='main')

if st.session_state["authentication_status"] == False:
    st.error('Username o Password errati')
elif st.session_state["authentication_status"] == None:
    st.warning('Per favore, effettua il login per visualizzare i dati')
elif st.session_state["authentication_status"]:
    # --- INIZIO AREA PROTETTA ---
    st.sidebar.title(f"Benvenuto {st.session_state['name']}")
    authenticator.logout('Logout', 'sidebar')
    
    st.title("🏗️ Gestione Avanzata Turni Cantiere")

    with st.expander("⚙️ 1. CONFIGURAZIONE RISORSE E ASSENZE", expanded=True):
        col1, col2 = st.columns([2, 1])
        with col1:
            st.subheader("👥 Personale e Abilitazioni")
            if 'df_personale' not in st.session_state:
                nomi = ["Gennaro Spada", "Michele Russo", "Tizio", "Caio", "Sempronio", "Bello"] + [f"Op {i:02d}" for i in range(7, 21)]
                default_data = [{"ID": n, "AB1": False, "AB2": False, "AB3": False, "Giorni Assenza": ""} for n in nomi]
                st.session_state.df_personale = pd.DataFrame(default_data)
            df_p = st.data_editor(st.session_state.df_personale, num_rows="dynamic", key="editor_p", use_container_width=True)
        with col2:
            st.subheader("📅 Periodo")
            anno = 2026
            mese_n = st.selectbox("Mese", range(1, 13), index=2)
            num_giorni = calendar.monthrange(anno, mese_n)[1]

    with st.expander("🛠️ 2. REQUISITI TURNI E ABILITAZIONI", expanded=True):
        req_data = {
            "Turno": ["Mattina", "Pomeriggio", "Notte"],
            "Personale Richiesto": [2, 2, 2],
            "Richiede AB1": [True, False, False],
            "Richiede AB2": [False, True, False],
            "Richiede AB3": [False, False, True]
        }
        df_req = st.data_editor(pd.DataFrame(req_data), use_container_width=True)

    if st.button("🚀 GENERA E OTTIMIZZA CALENDARIO", use_container_width=True):
        model = cp_model.CpModel()
        num_d = len(df_p)
        x = {}
        lavora = {}
        supera_soglia = {}
        # Pulizia assenze
        assenze_dict = {idx: [int(g.strip()) for g in str(row["Giorni Assenza"]).split(",") if g.strip().isdigit()] for idx, row in df_p.iterrows()}

        for d in range(num_d):
            lavora[d] = model.NewBoolVar(f'lavora_{d}')
            supera_soglia[d] = model.NewBoolVar(f'supera_{d}')
            for g in range(1, num_giorni + 1):
                for t in range(3):
                    x[d, g, t] = model.NewBoolVar(f'x_{d}_{g}_{t}')
                    model.AddImplication(x[d, g, t], lavora[d])

        for d in range(num_d):
            num_turni = sum(x[d, g, t] for g in range(1, num_giorni + 1) for t in range(3))
            model.Add(num_turni <= 20).OnlyEnforceIf(supera_soglia[d].Not())
        
        model.Minimize(sum(supera_soglia[d] * 100 for d in range(num_d)) + sum(lavora[d] * 10 for d in range(num_d)))

        for g in range(1, num_giorni + 1):
            for t_idx, t_row in df_req.iterrows():
                model.Add(sum(x[d, g, t_idx] for d in range(num_d)) == t_row["Personale Richiesto"])
                if t_row["Richiede AB1"]:
                    model.Add(sum(x[d, g, t_idx] for d in range(num_d) if df_p.iloc[d]["AB1"]) >= 1)
                if t_row["Richiede AB2"]:
                    model.Add(sum(x[d, g, t_idx] for d in range(num_d) if df_p.iloc[d]["AB2"]) >= 1)
                if t_row["Richiede AB3"]:
                    model.Add(sum(x[d, g, t_idx] for d in range(num_d) if df_p.iloc[d]["AB3"]) >= 1)
                for d in range(num_d):
                    if g in assenze_dict[d]:
                        model.Add(x[d, g, t_idx] == 0)

        for d in range(num_d):
            for g in range(1, num_giorni + 1):
                model.Add(sum(x[d, g, t] for t in range(3)) <= 1)
                if g < num_giorni:
                    model.Add(x[d, g, 2] + x[d, g+1, 0] <= 1)

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 10.0 
        status = solver.Solve(model)

        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            # --- CALCOLO CONFIGURAZIONE IDEALE ---
            total_slots_needed = df_req["Personale Richiesto"].sum() * num_giorni
            ideal_total_staff = -(-total_slots_needed // 20) # Arrotondamento per eccesso
            
            ideal_ab = {}
            for ab in ["AB1", "AB2", "AB3"]:
                if df_req[df_req[f"Richiede {ab}"] == True]["Personale Richiesto"].any():
                    # Servono almeno 3 persone per coprire i turni a rotazione h24/7 senza straordinari
                    ideal_ab[ab] = 3 
                else:
                    ideal_ab[ab] = 0

            # Messaggio di Benvenuto/Configurazione Ideale
            msg_ideale = f"👋 **Analisi di Cantiere Completata!**\n\n"
            msg_ideale += f"Per questi vincoli, l'ideale è inserire in organico un totale di **{ideal_total_staff} risorse** "
            dettagli_ab = [f"**{val} con {key}**" for key, val in ideal_ab.items() if val > 0]
            if dettagli_ab:
                msg_ideale += f"(di cui almeno {', '.join(dettagli_ab)}). "
            
            msg_ideale += "\n\n**Questa è la configurazione ideale per mantenere tutto il personale a 160 ore mensili SENZA prevedere costi di straordinario!**"
            
            st.info(msg_ideale)

            # --- VISUALIZZAZIONE RISULTATI ---
            st.subheader("📅 Calendario Turni Mensile")
            results_web, results_csv = [], []
            for g in range(1, num_giorni + 1):
                curr_date = date(anno, mese_n, g)
                row_web = {"Giorno": curr_date.strftime('%a %d')}
                row_csv = {"Data": curr_date.strftime('%d/%m/%Y')}
                for t_idx, t_name in enumerate(["Mattina", "Pomeriggio", "Notte"]):
                    staff = [df_p.iloc[d]["ID"] for d in range(num_d) if solver.Value(x[d, g, t_idx])]
                    row_web[t_name] = ", ".join(staff)
                    row_csv[t_name] = ", ".join(staff)
                results_web.append(row_web)
                results_csv.append(row_csv)
            
            st.table(pd.DataFrame(results_web))
            
            # --- ANALISI ORE ---
            st.divider()
            st.subheader("📊 Analisi Carico Ore")
            ore = {df_p.iloc[d]["ID"]: sum(solver.Value(x[d, g, t])*8 for g in range(1, num_giorni+1) for t in range(3)) for d in range(num_d)}
            st.bar_chart(pd.Series(ore))

            # Alert Straordinari (se la configurazione attuale non è quella ideale)
            overtime_staff = {nome: h for nome, h in ore.items() if h > 160}
            if overtime_staff:
                st.warning(f"⚠️ Attualmente hai **{sum(h-160 for h in overtime_staff.values())} ore** di straordinario. Confronta con la 'Configurazione Ideale' sopra!")
            
            # Download
            csv_buffer = io.StringIO()
            pd.DataFrame(results_csv).to_csv(csv_buffer, index=False, sep=";", encoding="utf-8-sig")
            st.download_button("📥 Scarica CSV per Excel", csv_buffer.getvalue(), f"Turni_{mese_n}.csv", "text/csv")
            
        else:
            st.error("❌ Soluzione non trovata. I vincoli sono troppo stretti per il personale attuale.")
