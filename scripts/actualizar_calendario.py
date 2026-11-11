match = DATE.search(s)
    if not match:
        return ""
    day, month, year = match.groups()
    if len(year) == 2:
        year = "20" + year
    try:
        return datetime(int(year), int(month), int(day)).date().isoformat()
    except ValueError:
        return ""


def candidates(tr):
    # Los nombres de equipos suelen ser enlaces de la tabla oficial.
    links = [normalized(a.get_text(" ", strip=True)) for a in tr.find_all("a")]
    links = [x for x in links if len(x) > 2 and not IGNORE.match(x) and not DATE.search(x)]
    if len(links) >= 2 and any(CABRAL.search(x) for x in links):
        return links
    # Alternativa para filas donde FUTGAL representa los equipos en celdas.
    cells = [normalized(c.get_text(" ", strip=True)) for c in tr.find_all(["td", "th"], recursive=False)]
    return [c for c in cells if 3 <= len(c) <= 90 and not IGNORE.match(c)
            and not DATE.search(c) and not HOUR.fullmatch(c)]


def parse_match(html, jornada):
    soup = BeautifulSoup(html, "html.parser")
    # Nunca importar si la página no parece la competición solicitada.
    for tr in soup.select("tr"):
        teams = candidates(tr)
        ours = [t for t in teams if CABRAL.search(t)]
        opponents = [t for t in teams if not CABRAL.search(t)
                     and not re.fullmatch(r"\d+\s*[-:]\s*\d+", t)]
        if not ours or not opponents:
            continue
        opponent = opponents[0]
        if len(opponent) < 3 or len(opponent) > 90:
            continue
        row_text = normalized(tr.get_text(" ", strip=True))
        context = row_text
        # FUTGAL a veces pone la fecha en un encabezado anterior.
        prev = tr.find_previous(["h3", "h4", "h5", "caption"])
        if prev:
            context += " " + normalized(prev.get_text(" ", strip=True))
        date = read_date(context)
        time_match = HOUR.search(row_text)
        time = (f"{int(time_match.group(1)):02d}:{time_match.group(2)}"
                if time_match else "")
        field_match = re.search(r"(?:campo|terreno de juego|instalaci[oó]n)\s*:\s*([^|;]+)", row_text, re.I)
        field = normalized(field_match.group(1))[:120] if field_match else ""
        return {
            "id": f"j{jornada}", "number": jornada,
            "rival": opponent, "date": date, "time": time,
            "field": field,
        }
    return None


def main():
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (compatible; CabralSchedule/1.0)"})
    matches = []
    failed = []
    for jornada in range(FIRST, LAST + 1):
        try:
            response = session.get(BASE, params={**PARAMS, "CodJornada": jornada}, timeout=20)
            response.raise_for_status()
            result = parse_match(response.text, jornada)
            if result:
                matches.append(result)
                print(f"J{jornada}: {result['rival']} / {result['date']} / {result['time']}")
            else:
                failed.append(jornada)
                print(f"J{jornada}: no se pudo identificar con seguridad el partido del Cabral")
        except requests.RequestException as exc:
            failed.append(jornada)
            print(f"J{jornada}: error de consulta: {exc}")

    if not matches:
        raise SystemExit("ERROR: sin partidos verificables. Se conserva calendario.json sin modificar.")

    # Conservamos jornadas válidas previas si FUTGAL falla temporalmente.
    previous = {}
    if OUT.exists():
        try:
            old = json.loads(OUT.read_text(encoding="utf-8"))
            previous = {int(m["number"]): m for m in old.get("jornadas", [])}
        except (ValueError, OSError, KeyError, TypeError):
            pass
    for match in matches:
        previous[match["number"]] = match
    result = {
        "actualizado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "origen": "FUTGAL · Segunda Benjamín Vigo · Grupo 2",
        "jornadas": [previous[n] for n in sorted(previous) if n >= FIRST],
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Actualizado calendario.json ({len(matches)} verificadas; {len(failed)} sin verificar)")


if __name__ == "__main__":
    main()
