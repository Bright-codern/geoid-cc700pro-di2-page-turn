// Decompile selected functions (by address) listed in a targets file.
// File format (one per line):  0xADDR  optional comment
// Usage: analyzeHeadless <proj> <name> -process cc700pro_app.elf -noanalysis \
//          -scriptPath <scripts> -postScript DecompileSelected.java <targets-file>
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.List;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileOptions;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;

public class DecompileSelected extends GhidraScript {

	@Override
	public void run() throws Exception {
		String[] args = getScriptArgs();
		if (args.length < 1) {
			println("usage: DecompileSelected.java <targets-file>");
			return;
		}
		List<String> lines = Files.readAllLines(Paths.get(args[0]));

		DecompInterface di = new DecompInterface();
		DecompileOptions opts = new DecompileOptions();
		di.setOptions(opts);
		di.toggleCCode(true);
		di.toggleSyntaxTree(false);
		if (!di.openProgram(currentProgram)) {
			println("ERROR decompiler openProgram failed");
			return;
		}

		int okCount = 0;
		for (String raw : lines) {
			String line = raw.trim();
			if (line.isEmpty() || line.startsWith("#") || line.startsWith("//")) {
				continue;
			}
			String[] parts = line.split("[\\s,;]+", 2);
			String addrStr = parts[0];
			String comment = parts.length > 1 ? parts[1].trim() : "";
			Address a;
			try {
				a = currentProgram.getAddressFactory().getAddress(addrStr);
			}
			catch (Exception e) {
				println("==BAD ADDR " + addrStr + "==");
				continue;
			}
			if (a == null) {
				println("==BAD ADDR " + addrStr + "==");
				continue;
			}
			Function f = getFunctionAt(a);
			if (f == null) {
				f = getFunctionContaining(a);
			}
			if (f == null) {
				println("==NO FUNC 0x" + a + "==");
				continue;
			}
			println("==FUNC 0x" + f.getEntryPoint() + " " + f.getName() +
				(comment.isEmpty() ? "" : " | " + comment) + "==");
			DecompileResults res = di.decompileFunction(f, 90, monitor);
			if (res == null || !res.decompileCompleted() || res.getDecompiledFunction() == null) {
				println("/* decompile failed: " +
					(res == null ? "null results" : res.getErrorMessage()) + " */");
			}
			else {
				println(res.getDecompiledFunction().getC());
				okCount++;
			}
			println("==END==");
		}
		println("DECOMPILED_OK " + okCount);
		di.dispose();
	}
}
