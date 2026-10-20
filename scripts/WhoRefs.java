// Resolve who references given addresses, following literal-pool hops.
// Usage: -postScript WhoRefs.java <addr-file>
// addr-file lines: 0xADDR optional-comment
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;

public class WhoRefs extends GhidraScript {

	private Set<String> visited = new HashSet<>();

	private void resolve(Address a, int depth, String indent) {
		if (depth > 3) {
			return;
		}
		String key = a.toString() + "/" + depth;
		if (!visited.add(key)) {
			return;
		}
		boolean any = false;
		for (Reference r : getReferencesTo(a)) {
			any = true;
			Address from = r.getFromAddress();
			Function f = getFunctionContaining(from);
			if (f != null) {
				println(indent + "CODE 0x" + from + " -> func 0x" + f.getEntryPoint() + " " +
					f.getName());
			}
			else {
				println(indent + "DATA 0x" + from + " (following)");
				resolve(from, depth + 1, indent + "  ");
			}
		}
		if (!any) {
			println(indent + "(no refs)");
		}
	}

	@Override
	public void run() throws Exception {
		String[] args = getScriptArgs();
		if (args.length < 1) {
			println("usage: WhoRefs.java <addr-file>");
			return;
		}
		List<String> lines = Files.readAllLines(Paths.get(args[0]));
		for (String raw : lines) {
			String line = raw.trim();
			if (line.isEmpty() || line.startsWith("#") || line.startsWith("//")) {
				continue;
			}
			String[] parts = line.split("[\\s,;]+", 2);
			Address a = currentProgram.getAddressFactory().getAddress(parts[0]);
			if (a == null) {
				println("== BAD " + parts[0]);
				continue;
			}
			String comment = parts.length > 1 ? parts[1] : "";
			println("== REFS-TO " + parts[0] + " " + comment);
			visited.clear();
			resolve(a, 0, "  ");
		}
		println("WHOREFS_DONE");
	}
}
