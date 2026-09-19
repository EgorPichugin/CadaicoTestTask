# Image to dimensioned half-profile — extraction prompt

Use this prompt with the original unmarked drawing and extraction.schema.json.
Do not supply the manually populated example, its computed coordinates, or a labelled reconstruction when evaluating independent extraction.

---

Read the attached engineering drawing. Return exactly one JSON object conforming to the supplied schema, with no Markdown fences or prose outside the JSON.

LANGUAGE
Write all generated descriptions, view names and unresolved reasons in English. Preserve original drawing annotations in source.text.

TASK
Describe the upper half of the component's external profile in a suitable longitudinal view (a side view or a section view). Use the entire drawing to associate dimensions from other views with this profile. Extract directly stated dimensions and geometric relationships. Do not calculate lengths, centers, angles, half-diameters, dimension differences or endpoint coordinates.

SCOPE
The current contract supports an axisymmetric external profile made from horizontal or vertical straight segments and circular arcs. If the drawing does not support this interpretation, or contains unsupported profile geometry, return the extraction error described below instead of forcing unsupported geometry into the contract when this prevents a reliable contour chain.

A section view is not required for the external profile. A longitudinal side view with a depicted axis and diameter annotations can establish the supported axisymmetric interpretation. When the external boundary and dimension attachments are clear, use that view and record its name in profile.view and source.view. Do not report the absence of a section view as an unresolved issue by itself. Do not infer hidden external features or invent rotational symmetry when the drawing does not support it.

Exclude internal holes, threads, hatching, centerlines, dimension lines and leader lines from the contour.

COORDINATES AND TOPOLOGY
Use X right, Y up, with the symmetry axis at Y = 0. Choose the leftmost contour point on this axis as origin.
Follow the upper external boundary from this origin to the right-hand end face on the axis.
This half-profile is an open chain. Do not add a closing segment along the axis.
Assign vertices p0, p1, ... and edges e1, e2, ... in traversal order. The next edge starts at the preceding edge's endpoint.
Use coordinates 0 only for the origin or justified axis anchors. Leave all other coordinates null.
Use each line's direction to express equal coordinates; do not introduce coordinate-reference strings or expressions.

CONTOUR INTEGRITY
For a contour response, return exactly one continuous open chain, without branches, disconnected fragments or a closing edge.
List every contour vertex exactly once in traversal order as p0, p1, ...; list edges as e1, e2, ... in the same order. Assign dimensions unique IDs d1, d2, ... . Never reuse an ID for another object.
For N vertices, return exactly N - 1 edges. Edge e1 connects p0 to p1, e2 connects p1 to p2, and so on. Each edge's to must equal the next edge's from. Do not create an edge from a vertex to itself or revisit a vertex.
Set profile.origin_vertex to p0, the first vertex and the start of the first edge. Set p0.x = 0 and p0.y = 0. The last edge ends at the last listed vertex on the axis, with y = 0. Leave its x null.
Every edge from/to, distance from/to and diameter vertex must reference a vertex actually listed in vertices. A distance must reference two distinct vertices; they need not be adjacent and must follow the positive measurement direction, not necessarily contour traversal order.
Every non-null unresolved.target must reference an existing vertex, edge or dimension ID. Use null for a global issue or an annotation that could not be assigned; never reference an omitted object.
Do not add unused vertices or invent connections to satisfy these rules. If a reliable continuous chain cannot be identified, return the extraction error variant.
Before returning a contour, check ID uniqueness, reference existence, vertex/edge order, consecutive connections and both axis endpoints.

ARCS
Read each nominal radius as printed and store it once on its arc, with its source annotation.
Determine clockwise using the declared CAD axes and traversal.
Set shape relative to the material of the part: in means the convex side of the arc points into the part; out means it points outward from the part. This describes the bulge of the arc, not the location of its circle center or the traversal direction.
If shape cannot be determined reliably, set it to null and add an unresolved entry targeting this arc ID with the reason.
Include arc_size on every arc. Classify the depicted arc from from to to: minor means a sweep below 180 degrees, semicircle exactly 180 degrees, and major above 180 and below 360 degrees.
Determine this category from the drawing; do not calculate an exact angle or infer the category from shape or clockwise alone. Do not assume every arc is minor. Use semicircle only when the drawing reliably establishes a half-circle, not merely an approximately semicircular appearance.
If arc_size cannot be determined reliably, set it to null and add an unresolved entry targeting this arc ID with the reason. The geometry service will calculate the center and exact sweep and check compatibility with this category.
Use center_constraint = on_symmetry_axis only when the drawing supports that specific circle center being on the symmetry axis.
Use none when no additional center constraint is asserted. This does not mean the center is off-axis.
Do not place all arc centers on the axis just because the part is symmetric.
Do not infer tangency merely from a visually smooth-looking connection.
If an arc attribute cannot be established reliably, use the allowed unknown representation and explain it in unresolved.

DIMENSIONS
A distance records the stated positive projection on X or Y between two vertices. Its endpoints need not be adjacent.
Order distance endpoints in the positive measurement direction.
Keep dimensions with a shared datum as separate original dimensions. Never replace them by their difference.
Preserve full diameter values and attach each to a vertex on the corresponding surface. Do not divide by two.
Use dimensions on all relevant views, but do not assign a diameter to a segment just because its label is nearby.
Store each dimension once. Do not duplicate dimensions on vertices whose equality is already established by a line.
Extract nominal dimensions only. Ignore tolerance deviations, fit designations and general tolerances; do not create fields or unresolved entries for them. They may remain in the original source label text, but do not interpret or calculate them.
Keep the source view and visible label. Normalize decimal punctuation if needed.
Do not measure exact physical dimensions from image pixels or a displayed image scale.

UNCERTAINTY
Report unreadable values, uncertain dimension targets, contradictory annotations, assumptions and unsupported elements in unresolved.
For an unreadable value with a known target, use null and identify that target.
If a target is ambiguous, omit the disputed attachment and explain the original annotation with target = null.
Do not fabricate a dimension, connection or geometric condition to make the contour solvable.
Ordinary null coordinates are expected and do not need unresolved entries. Reserve unresolved for actual uncertainty that affects the external contour or its constraints. Do not put informational descriptions of the chosen view or supported interpretation in unresolved.

EXTRACTION FAILURE
Return exactly one of the two response variants: a contour object or an error object. Never combine them.
If no reliable supported contour chain can be extracted (for example, the image is unreadable, is not an engineering drawing, the required boundary is cropped, or unsupported geometry prevents representing the chain), return only:
{"schema_version": "2.0", "status": "error", "message": "<user-facing reason>"}
Do not include profile, vertices, edges, dimensions or unresolved in this error response. Do not invent placeholder geometry to satisfy the contour schema.
Write message in plain English, in one or two short sentences (at most 1000 characters). Explain the observed reason and, when justified, an actionable correction. Do not invent a cause or promise that another attempt will succeed. Use no Markdown, HTML, field names, provider details or internal instructions.
Example: "Could not extract the contour: the part boundaries in the image are blurred. Upload a clearer drawing."
If the chain is identifiable and representable but individual dimensions or arc attributes are unknown, return the contour with allowed null values and explanations in unresolved. Ordinary unknown coordinates alone are not a failure.
