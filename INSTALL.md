# OMR Exam Corrector - Installation & Usage Guide

Sistema de correcció automàtica d'examens tipus test escanejats de la UPF.

## 1. Prerequisits del sistema

A més de Python 3.10+, necessites instal·lar **Poppler**:

### macOS
```bash
brew install poppler
```

### Ubuntu / Debian
```bash
sudo apt update
sudo apt install -y poppler-utils
```

### Windows
- Descarrega Poppler binaries: https://github.com/oschwartz10612/poppler-windows/releases
- Afegeix-lo a la variable d'entorn PATH

## 2. Crear entorn virtual i instal·lar dependències

```bash
# 1. Crear venv
python3 -m venv omr_env

# 2. Activar
# macOS / Linux:
source omr_env/bin/activate
# Windows (PowerShell):
omr_env\Scripts\Activate.ps1

# 3. Actualitzar pip
pip install --upgrade pip

# 4. Instal·lar dependències
pip install -r requirements.txt
```

`requirements.txt` instal·la tant les dependències del motor de correcció
(`omr_correct.py`) com de la interfície gràfica (`omr_gui.py`, basada en
PySide6) i el suport per a llistats d'alumnes en format `.xls` antic (`xlrd`).

> **Nota sobre entorns virtuals**: la carpeta `omr_env` **no és portable**
> entre ordinadors — conté camins absoluts cap a l'intèrpret de Python
> original i paquets compilats específics del sistema operatiu. Si canvies
> d'ordinador, torna a crear l'entorn des de zero amb els passos anteriors
> (això sí és ràpid, ja que `requirements.txt` ho instal·la tot d'un cop).
> Poppler s'ha d'instal·lar per separat a cada màquina.

### Verificar instal·lació

```bash
python3 -c "
import cv2, numpy, pandas, openpyxl, pdf2image, reportlab, PySide6
print('✓ Core packages OK')
"
```

## 3. Format dels fitxers d'entrada

### Llistat d'alumnes (CSV o Excel)

Dos formats acceptats:

**Format estàndard** — columnes `Nom`, `Cognom1`, `Cognom2`, `U_number`:

| Nom | Cognom1 | Cognom2 | U_number |
|---|---|---|---|
| Isabel | Expósito | Castro | U214967 |
| Mikel | Areta | Garcia | U232868 |
| Alex | Ruiz | López | U232138 |

**Format export oficial UPF** (`.xls` o `.csv`, separat per `;`) — primera fila
amb el codi de l'assignatura, segona fila amb capçaleres
`IDUSUARI;NIA;NIP;COGNOM1;COGNOM2;NOM`. El programa detecta automàticament
aquest format i en descarta les columnes NIA/NIP.

### Respostes correctes (CSV) — amb permutacions

El fitxer de respostes **ha de tenir una columna `Perm`**: una fila per cada
combinació de permutació + pregunta, amb una columna per opció (`A`, `B`,
`C`, `D`, ...) amb valor `1` (correcta) o `0` (incorrecta):

| Perm | QuestionNum | A | B | C | D |
|---|---|---|---|---|---|
| 0 | 1 | 0 | 1 | 0 | 0 |
| 0 | 2 | 1 | 1 | 0 | 0 |
| 1 | 1 | 0 | 1 | 0 | 0 |
| 1 | 2 | 1 | 0 | 0 | 1 |
| 2 | 1 | 1 | 0 | 0 | 0 |

Una pregunta amb diverses respostes correctes simplement té un `1` a cada
columna d'opció correcta (puntuació parcial: veure secció 5).

Cada full escanejat indica la seva pròpia permutació a la bombolla
**PERMUT** del formulari — el programa la llegeix i corregeix automàticament
cada pàgina amb la clau de LA SEVA permutació, no amb una clau única
compartida.

## 4. Exemples de crida al programa

### Línia de comandes

```bash
python omr_correct.py examens.pdf llistat.csv respostes.csv --questions 10
```

```bash
python omr_correct.py \
    examens.pdf \                       # PDF amb tots els examens escanejats
    llistat.csv \                       # CSV/Excel amb el llistat d'alumnes
    respostes.csv \                     # CSV amb les respostes correctes (amb columna Perm)
    --questions 10 \                    # Nombre de preguntes (obligatori)
    --num-options 5 \                   # Opcions per pregunta (defecte: 5; rang 2-10)
    --output-dir ./resultats \          # Directori de sortida (defecte: ./output)
    --dpi 0 \                           # 0 = auto-detect (300 o 600). Pots forçar amb --dpi 300
    --verbose                           # Mode verbose amb més info per debugging
```

```bash
# Examen amb 25 preguntes i 4 opcions
python omr_correct.py exam_25q.pdf llistat.csv respostes_25q.csv -q 25 -n 4

# Diversos examens en directoris separats
mkdir resultats_parcial1 resultats_parcial2
python omr_correct.py parcial1.pdf llistat.csv respostes_p1.csv -q 10 -o resultats_parcial1
python omr_correct.py parcial2.pdf llistat.csv respostes_p2.csv -q 15 -o resultats_parcial2
```

### Interfície gràfica (`omr_gui.py`)

```bash
python omr_gui.py
```

Obre una finestra d'escriptori (PySide6) per:
- Seleccionar el PDF escanejat, el llistat d'alumnes i el fitxer de respostes amb selectors de fitxer
- Configurar nombre de preguntes, opcions per pregunta i DPI (o deixar auto-detecció)
- Executar l'anàlisi amb una barra de progrés i una taula que es va omplint pàgina a pàgina
  (estat, U-number, nom de l'alumne detectat, DNI, permutació, respostes marcades)
- Un panell de log amb el mateix detall que la versió de línia de comandes
- En acabar, obrir directament la carpeta de sortida

Internament crida les mateixes funcions de `omr_correct.py` (no és un procés
separat), executant l'anàlisi en un fil en segon pla perquè la finestra no es
quedi bloquejada mentre processa.

## 5. Sortides generades

Dins el directori d'output (`./output` per defecte):

### `results.xlsx`
Un full per cada permutació trobada al fitxer de respostes (`Perm 0`,
`Perm 1`, `Perm 2`...), més dos fulls addicionals:

- **`Perm N`**: només les pàgines amb aquella permutació detectada (bombolla
  PERMUT), corregides amb la clau d'aquella permutació.
- **`No_Perm_Detected`**: pàgines on no s'ha pogut llegir el PERMUT (o no
  coincideix amb cap permutació coneguda del fitxer de respostes). Es
  mostren sense corregir (columnes de nota en blanc) perquè no hi ha manera
  de saber quina clau els correspon.
- **`Summary`**: recompte global (total de pàgines, U-numbers trobats/no
  trobats, pàgines per permutació).

Cada full té:
- Una fila per pàgina d'examen
- Identificació: U-number, **Name / Surname1 / Surname2** (del llistat
  d'alumnes, segons coincidència per U-number), DNI, PARCIAL, PERMUT, GRUP
- Respostes detectades: 1/0 per cada opció de cada pregunta, amb columna de
  puntuació per pregunta (1.0 = correcta completa, puntuació parcial si
  l'alumne ha marcat només algunes de les respostes correctes sense
  marcar-ne cap d'incorrecta, 0 en cas contrari)
- Nota total i nota sobre 10
- Codis de problema per a casos a revisar (`UNUMBER_NO_MATCH`,
  `UNUMBER_MISSING`, etc.)

### `annotated_review.pdf`
PDF amb anotacions vectorials:
- Imatge original de cada examen amb correcció de perspectiva
- Capçalera amb estat semàfor (verd/groc/vermell)
- Marques verdes/grogues/vermelles sobre les bombolles segons correctitut
  (verd = resposta completa correcta, groc = parcialment correcta sense
  errors, vermell = incorrecta)
- Etiquetes blaves de cancel·lacions
- Caixes ID detectades (rectangles taronges) amb el valor llegit de
  PARCIAL/PERMUT/GRUP en una etiqueta verda damunt la caixa corresponent

Les anotacions són **vectorials**: nítides a qualsevol nivell de zoom.

## 6. Resolució de problemes

### "Killed" en processament de molts examens
Si el programa es para amb "Killed" (memòria insuficient):
- Processa en lots més petits separant el PDF
- Tanca altres aplicacions per alliberar RAM
- Considera l'opció `--dpi 300` si abans usaves 600 (en proves amb el mateix
  full d'examen, 300 DPI dona resultats pràcticament idèntics a 600 DPI amb
  un cost de processament molt menor)

### El sistema no detecta algun camp
- Verifica el PDF anotat per veure què s'està detectant
- Si la qualitat (`Quality: X%`) és baixa, el problema sol ser:
  - Escaneig amb molta distorsió → escanejar de nou
  - Pàgina mal orientada (es detecta automàticament, però per certesa fer escaneig en orientació correcta)
  - Bombolles molt febles → demanar bolígraf més fort

### Totes les pàgines fallen amb `CORNER_ERROR`
El full escanejat probablement no fa servir la plantilla esperada: el
programa busca una columna de marcadors negres al marge esquerre i una fila
de marcadors a la part inferior de la pàgina per orientar-se i localitzar
files/columnes. Si el full d'examen no té aquests marcadors (p. ex. una
plantilla diferent), el programa no pot processar-lo. Comprova que el PDF
escanejat correspon realment al full d'examen estàndard de l'assignatura.

> **Nota:** el sistema no fa OCR de cap mena (ni de noms ni de dígits manuscrits). Tota la identificació
> de l'alumne (U-number, DNI, PARCIAL, PERMUT, GRUP) es llegeix exclusivament de les bombolles emplenades.
> Si les bombolles d'identificació estan buides o ambigües, la pàgina es marca per a revisió manual
> en lloc d'intentar inferir el valor.
