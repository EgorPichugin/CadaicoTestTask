# CADAICO Backend

FastAPI service for extracting and calculating reproducible CAD contours from technical drawings.

## Process a drawing locally

The complete pipeline can run from PowerShell without starting FastAPI. It
validates the image, sends it to the configured LLM, calculates the closed
contour and exports the result as JSON and DXF.

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Add your OpenAI API key to `.env`, then run:

```powershell
python -m app.cli.process_drawing
```

A standard Windows file picker opens. Select a JPG, PNG or WebP drawing. For
scripts and automated runs, the image path can still be passed directly:

```powershell
python -m app.cli.process_drawing "C:\path\to\drawing.jpg"
```

By default, a new `drawing_result` directory is created next to the image:

```text
drawing_result/
├── extraction_result.json
├── geometry_result.json
└── contour.dxf
```

Use `--output` to select a different directory:

```powershell
python -m app.cli.process_drawing drawing.jpg --output results\drawing-01
```

The output directory must not already exist, so a previous run is never
overwritten. `contour.dxf` is created only when geometry status is `Success`.
For `Unresolved`, `Ambiguous` or `Invalid`, both JSON files are saved with the
available evidence and issues, and the command exits with code `2`. Input,
configuration or extraction errors exit with code `1` without publishing a
partial result directory.

This command does not start an HTTP server, but image recognition still uses the
OpenAI API and therefore requires `OPENAI_API_KEY` and an internet connection.

## Run in Windows PowerShell

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --env-file .env
```

Once the server is running:

- API: http://127.0.0.1:8000
- Swagger UI documentation: http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/health

## Extract data from a drawing

The endpoint accepts JPEG, PNG or WebP files up to 10 MB:

```text
POST /api/v1/extractions
Content-Type: multipart/form-data
form field: file
```

`DrawingAnalysisClient` connects to the OpenAI Responses API through dependency
injection, using model `gpt-6-astra`, `reasoning.effort = medium` and image
`detail = original`. Set `OPENAI_API_KEY` in the process environment before
starting the server. In PowerShell, you can enter the key without displaying it
or saving its value in command history:

```powershell
$openAiKey = Read-Host "OpenAI API key" -MaskInput
$env:OPENAI_API_KEY = $openAiKey
Remove-Variable openAiKey
uvicorn app.main:app --reload
```

`-MaskInput` requires PowerShell 7.1+. For the API, load `.env` with `--env-file .env`.
Without a key, extraction returns HTTP 503 with an explanatory message; `/health`
remains available.

The client uses the official SDK's `AsyncOpenAI.responses.parse()` with the
Pydantic `ExtractionResponse` model. The SDK generates the schema and parses the
response. The client sends the image, prompt and schema to OpenAI. Structured
Outputs uses a `result` wrapper, which the client removes before returning the
data to the service. Requests use `store=false`, a 180-second timeout and a
16,000-token output limit including reasoning. Automatic retries are disabled.
Incomplete responses, refusals and invalid JSON are not returned as contours.
Analysis errors return HTTP 502, timeouts return 504, and extraction failures
with an explanation return 422. Tests use dependency overrides to supply mock clients.

Documentation: [model](https://developers.openai.com/api/docs/models/gpt-6-astra),
[Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs).

The `DrawingProcessingService` pipeline is `DrawingImageValidator` →
`ContourExtractionService` → `GeometryCalculationService`. Each stage is connected
through dependency injection. Extraction returns an `ExtractionResult`, which is
passed to `calculate(extraction)`. The API output contains `geometry` with a
`GeometryResult` and `dxf` with the ready-to-download CAD file content.
`GeometryResult` contains `units`, `profile`, `status`, `is_closed`, `issues`,
`vertices` and `edges`, without the original dimensions. The input
`ExtractionResult` is not modified.

The API returns HTTP 200 when geometry calculation completes, including when the
constraints cannot be solved. Clients must check `status`:

| Status | Meaning |
| --- | --- |
| `Success` | The complete closed contour has been calculated and checked. |
| `Unresolved` | Calculation is incomplete; this does not prove that no solution exists. |
| `Ambiguous` | More than one valid geometry remains. |
| `Invalid` | The input is invalid or the constraints contradict each other. |

Only `Success` includes calculated vertices and edges, with `is_closed = true`,
and a non-null DXF string. The DXF contains native `LINE` and `ARC` entities in
millimetres. Frontend clients download this value directly instead of
recalculating CAD entities. Other statuses return `dxf = null`, empty geometry
lists, `is_closed = false`, and explanations in `issues`; each issue contains a
`target` ID (or `null` for a global issue) and a `reason`. Image validation and
extraction failures retain their HTTP error responses described above.

The successful result contains the upper profile followed by its reflection
about the X axis, traversed back to the origin. Points on the axis are shared.
A line includes its length; an arc includes its radius, center, direction,
`shape`, `arc_size` and a positive sweep angle in degrees. `profile` describes
the input half; `vertices` and `edges` describe the complete contour. Adjacent
edges share a point; tangency is not assumed.

Calculation uses separate handlers for dimensions, lines and arcs. They repeatedly
apply known constraints to shared calculation state until a complete pass adds no
new values. A known coordinate is checked against new evidence rather than silently
overwritten. Arc candidates are checked against the radius, traversal direction,
`shape`, `arc_size`, center constraints and the upper-half boundary. The service
does not assume that an unknown `arc_size` means `minor`.

Numerical comparisons use an absolute tolerance of `1e-7` mm, independent of
manufacturing tolerances. The final contour is checked for nonzero area,
continuity, arc consistency, overlaps and self-intersections using lines and
circles directly, without approximating arcs by a polygon. Recorded extraction
uncertainty remains in `issues`: a unique geometric fit does not confirm an
uncertain dimension attachment. If multiple valid contours are established,
the result is `Ambiguous` even when an extraction issue was also recorded.

If these passes stop with unresolved coordinates, a bounded SymPy fallback solves
the remaining equations together: it eliminates linear dependencies, then solves
finite polynomial systems. This fallback supports at most four remaining variables
and 16 nonlinear equations; candidate search is limited to 256 states. Free
parameters, unsupported systems and exhausted limits produce `Unresolved`, rather
than a guessed contour. This is a solver for the supported extraction format, not
an unrestricted CAD constraint solver.
The fallback solves exact equations built from the available decimal values;
rounding can therefore leave a coupled system `Unresolved` even when a solution
within numerical tolerance might exist.

## Tests

```powershell
pytest
```

## Response schema

The models in `app/models/extraction.py` are the source of truth for the schema.
The JSON schema files are documentation exports; the application does not read
them at startup. After changing the models, update both copies:

```powershell
python -m app.contracts.export_schema
```
