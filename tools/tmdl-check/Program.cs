// tmdl-check: reads a semantic model's TMDL folder with Microsoft's own TMDL serializer (TOM).
// Any syntax or reference error fails the check. With --bim, it also writes the model as model.bim,
// which the Best Practice Analyzer and the team rules read.
//
// Usage: dotnet run --project tools/tmdl-check -- "<Name>.SemanticModel" [--bim out/model.bim]
using Microsoft.AnalysisServices.Tabular;
using Microsoft.AnalysisServices.Tabular.Tmdl;

if (args.Length < 1)
{
    Console.Error.WriteLine("usage: tmdl-check <item.SemanticModel folder> [--bim <out.bim>]");
    return 2;
}
var item = args[0].TrimEnd('/', '\\');
var definition = Path.Combine(item, "definition");
string bim = null;
for (int i = 1; i < args.Length - 1; i++)
    if (args[i] == "--bim") bim = args[i + 1];

if (!Directory.Exists(definition))
{
    Console.WriteLine($"::error file={item}::No definition folder in {item}");
    return 1;
}

Database db;
try
{
    db = TmdlSerializer.DeserializeDatabaseFromFolder(definition);
}
catch (TmdlFormatException e)
{
    var file = DocPath(definition, e.Document);
    Console.WriteLine($"::error file={file},line={e.Line}::TMDL syntax error: {Clean(e.Message)}");
    return 1;
}
catch (TmdlSerializationException e)
{
    var file = DocPath(definition, e.Document);
    Console.WriteLine($"::error file={file},line={e.Line}::TMDL error: {Clean(e.Message)}");
    return 1;
}
catch (Exception e)
{
    Console.WriteLine($"::error file={definition}::Model could not be read: {Clean(e.Message)}");
    return 1;
}

var m = db.Model;
int measures = m.Tables.Sum(t => t.Measures.Count);
int columns = m.Tables.Sum(t => t.Columns.Count);
Console.WriteLine($"TMDL ok: {item} ({m.Tables.Count} tables, {columns} columns, {measures} measures, {m.Relationships.Count} relationships)");

if (bim != null)
{
    Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(bim)));
    db.Name ??= Path.GetFileName(item).Replace(".SemanticModel", "");
    db.ID ??= db.Name;
    File.WriteAllText(bim, JsonSerializer.SerializeDatabase(db));
    Console.WriteLine($"wrote {bim}");
}
return 0;

static string DocPath(string definition, string doc)
{
    if (string.IsNullOrEmpty(doc)) return definition;
    doc = doc.TrimStart('.', '/', '\\');
    if (!doc.EndsWith(".tmdl")) doc += ".tmdl";
    return Path.Combine(definition, doc);
}

static string Clean(string s) => s.Replace("\r", " ").Replace("\n", " ");
