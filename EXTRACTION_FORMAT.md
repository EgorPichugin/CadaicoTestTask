# LLM response format: contour, version 2.0

Start with the [complete example](extraction.example.json). This is a manually prepared description of Drehteil.jpg, **not an actual model response or an independently verified reference**.

## Purpose

The LLM reads dimensions and describes the elements they belong to. Code later calculates coordinates, line lengths and circle centers. The original response is stored separately from the calculated geometry.

The initial implementation supports the **upper half of an external axisymmetric profile**, consisting of horizontal/vertical lines and circular arcs. Associating diameters with the section relies on this part being axisymmetric. This is not a universal format for arbitrary CAD drawings.

## Overall structure

| Section | Contents |
| --- | --- |
| `profile` | Selected view, upper half, symmetry axis and origin |
| `vertices` | Points with IDs and unknown coordinates |
| `edges` | Lines and arcs in traversal order; radii are stored on arcs |
| `dimensions` | Distances between vertices and diameters |
| `unresolved` | Unresolved ambiguities, unreadable dimensions and unsupported elements |

Like `edges`, `vertices` is a list of objects with an `id`. Its length is not fixed to a particular image. Code can easily convert it into a dictionary keyed by ID. References use IDs rather than array positions.

## Coordinate system and half-profile

- X points right along the part; Y points up. The symmetry axis is Y = 0.
- The origin is the leftmost profile point on the axis, identified by `origin_vertex`.
- This point has `x: 0, y: 0`. The chain endpoint is also on the axis: `y: 0`.
- Other coordinates remain `null`. Values such as 31, 10 or 1.253981 are not recorded as coordinates during extraction.
- Zero is a known coordinate; `null` means not yet calculated. An unknown coordinate is not an error by itself.
- The chain is **open**, from the left point on the axis to the right end face on the axis. Do not add a closing segment along the axis.
- The full external contour is obtained by mirroring the upper chain and traversing the mirrored part in reverse. Mirroring alone reverses an arc's direction; reverse traversal reverses it again.
- The example lists vertices in traversal order. IDs do not encode numerical coordinates and must not be used for formulas hardcoded to a particular part.

## Example vertices

| ID | Position on the contour |
| --- | --- |
| p0 | Leftmost point of the R40.5 arc, on the axis |
| p1 | Transition from R40.5 to the upper horizontal line of the wide head |
| p2 | Transition from that line to R9 |
| p3 | End of R9 at the lower point of the step |
| p4 | Upper point of the step, start of the central cylindrical section |
| p5 | End of the central section before the downward step |
| p6 | Lower point of that step |
| p7 | Upper point of the right end face |
| p8 | Right end face on the axis |

## Line

```json
{"id": "e2", "type": "line", "from": "p1", "to": "p2", "direction": "+X"}
```

`+X` means equal Y coordinates and movement to the right. `-X` means equal Y coordinates and movement to the left. `+Y` and `-Y` mean equal X coordinates and upward/downward movement.

An expression such as `"p2.y": "p1.y"` is therefore unnecessary. Coordinate equality works both ways: a known value on either side determines the other. Direction also constrains the sign of the coordinate difference; a segment must not have zero length.

There is no `length` field: code calculates the length. If the drawing explicitly states it, it is recorded in `dimensions` as a dimension between the line endpoints.

## Arc

```json
{
  "id": "e1",
  "type": "arc",
  "from": "p0",
  "to": "p1",
  "radius": 40.5,
  "clockwise": true,
  "shape": "out",
  "arc_size": "minor",
  "center_constraint": "on_symmetry_axis",
  "source": {"view": "section_A_A", "text": "R40.5"}
}
```

- `radius` is a value read from the drawing, not a calculated result. Do not duplicate the radius in `dimensions`.
- `clockwise` describes clockwise traversal from `from` to `to` **with X pointing right and Y pointing up**.
- `shape: "in"` means the convex side of the arc points into the part; `shape: "out"` means it points outward. This is neither the circle center location nor the traversal direction.
- `shape: null` means the shape cannot be determined; an entry in `unresolved` with the arc ID and a reason is required.
- `arc_size` is a required arc category: `"minor"` means below 180°, `"semicircle"` exactly 180°, and `"major"` above 180° but below 360°. This is a separate attribute and does not replace `shape` or `clockwise`.
- The LLM determines the category from the image without calculating the exact angle or center. Do not automatically classify all arcs as minor; use semicircle only with reliable evidence, not approximate visual resemblance.
- `arc_size: null` means the category cannot be established; an entry in `unresolved` with the arc ID and a reason is required. Geometry calculation must check the category together with the other constraints.
- Older responses without `arc_size` do not meet the updated contract: extract the field from the drawing or explicitly set it to `null` with an explanation in `unresolved`.
- `center_constraint: "on_symmetry_axis"` adds a constraint: the circle center lies on the axis. The first arc needs this because its upper endpoint is not fully determined yet.
- `center_constraint: "none"` means **no additional center constraint**, not that the center is off-axis. For R9, the endpoints, radius and selected arc determine the center.
- `center_constraint: "unknown"` is allowed when ambiguous and requires an entry in `unresolved`.
- The center must still be calculated for both arcs. Global symmetry does not automatically place every arc center on the axis.
- Tangency is not assumed by default. This example has no additional tangency constraints.

## Distances

```json
{
  "id": "d2",
  "type": "distance",
  "from": "p2",
  "to": "p8",
  "axis": "X",
  "value": 26,
  "source": {"view": "section_A_A", "text": "26"}
}
```

This is the **distance projected onto X**: `p8.x - p2.x = 26`. It is not the direct distance between these points. Vertices need not be adjacent.

Record dimensions as positive values. For X, `from` is the left point and `to` is the right point; for Y, they are the lower and upper points respectively. Code calculates derived distances, such as the difference between 31 and 26.

## Diameters from another view

```json
{
  "id": "d5",
  "type": "diameter",
  "vertex": "p1",
  "value": 20,
  "source": {"view": "front", "text": "Ø20 h7"}
}
```

The diameter belongs to the surface containing the specified section vertex. The axis is already defined globally in `profile.symmetry_axis`. For the upper half, code derives `y = value / 2`.

The LLM must associate the surface in another view with the correct section vertex. The Ø20 label alone does not prove that this association is correct.

Store each dimension once. For example, associating Ø15 with p4 is sufficient: horizontal segment e5 establishes that p4 and p5 have equal Y coordinates.

## Nominal dimensions and sources

- `value` and `radius` contain nominal values only.
- Tolerances, deviations and fit designations are not extracted and do not require entries in `unresolved`.
- `source.view` and `source.text` preserve the view and original annotation. The annotation may contain tolerance designations, but these are not interpreted. Decimal commas may be normalized to decimal points.
- For an arc, `source` refers to its radius. Recording an annotation source does not independently confirm that the data is correct.

## Ambiguities

```json
{
  "unresolved": [
    {"target": "e3", "reason": "The arc radius cannot be read."}
  ]
}
```

In this case, `e3.radius` is `null`. An unknown radius, line direction, arc traversal direction/shape/category (`arc_size`) or dimension value requires an explanation. Unknown coordinates represented by `null` are expected.

If a dimension's target is unclear, do not assign an arbitrary vertex: omit the uncertain association and add an entry with `target: null`. Report unconfirmed symmetry, assumptions and unsupported elements in the same way.

A nonempty `unresolved` list means the contour cannot be presented as fully confirmed. Conversely, an empty list does not prove that the model missed nothing: subsequent checks must establish this.

## Files and validation

- [Example](extraction.example.json): a manual description of this part.
- [JSON Schema](extraction.schema.json): the response structure exported from Pydantic; do not edit manually. Update it from the backend project root with `python -m app.contracts.export_schema`. The client uses `responses.parse()` and `ExtractionResponse`; request compatibility has been tested with the SDK and mocked HTTP, but a live API call has not yet been verified.
- [LLM instructions](EXTRACTION_PROMPT.md): a prompt without a completed solution or this part's numerical values. Supply it with the image and schema, **without the manual example when independently evaluating extraction**.
- [Validation](checks/verify_contract.py): checks the schema, references and numerical consistency of the manual example. This is not a general CAD solver or a recognition implementation.
- [Validation dependency](requirements-dev.txt): a JSON Schema validator.

Run validation after installing the dependency:

```text
python -m pip install -r requirements-dev.txt
python checks/verify_contract.py
```

Validating the manual example shows that the recorded constraints are sufficient to construct its geometry numerically. It does not prove that the LLM will extract them correctly or that associations between views have been independently confirmed. Numerical check tolerances control calculations; they do not state the accuracy of drawing recognition.

## Extraction failure

If a reliable contour chain cannot be extracted, the model returns a separate response without geometry:

```json
{"schema_version": "2.0", "status": "error", "message": "Could not extract the contour: the part boundaries in the image are blurred. Upload a clearer drawing."}
```

`message` is nonempty English text of up to 1000 characters: the reason and, when possible, a suggested correction. The response contains no `profile`, `vertices`, `edges`, `dimensions` or `unresolved`. A successful response retains the existing structure. If the chain is identifiable, unknown individual dimensions remain in `unresolved` and do not require failure by themselves.

The service converts this response into `ContourNotExtractedError`. The API returns HTTP 422 with `{"detail": "..."}`; the interface should display `detail` to the user as plain text, not HTML.
