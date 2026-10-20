// Scan instructions for an immediate value loaded into a register, print context.
// Usage: -postScript FindMoviVal.java <value> <register>
import ghidra.app.script.GhidraScript;
import ghidra.program.model.lang.Register;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.scalar.Scalar;

public class FindMoviVal extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        long want = Long.decode(args[0]);
        Register reg = currentProgram.getRegister(args.length > 1 ? args[1] : "a10");
        println("SCAN value=" + Long.toHexString(want) + " reg=" + reg);
        InstructionIterator it = currentProgram.getListing().getInstructions(true);
        int count = 0;
        while (it.hasNext()) {
            Instruction ins = it.next();
            String mn = ins.getMnemonicString();
            if (!(mn.startsWith("movi") || mn.equals("mov"))) continue;
            if (ins.getNumOperands() < 2) continue;
            Object[] ops = ins.getOpObjects(0);
            if (ops.length == 0 || !reg.equals(ops[0])) continue;
            Object[] vals = ins.getOpObjects(1);
            if (vals.length == 0 || !(vals[0] instanceof Scalar)) continue;
            long v = ((Scalar) vals[0]).getUnsignedValue();
            if (v != want) continue;
            Function f = getFunctionContaining(ins.getAddress());
            println("HIT " + ins.getAddress() + " " + ins + " in " +
                (f == null ? "?" : f.getEntryPoint() + " " + f.getName()));
            Instruction next = ins;
            for (int i = 0; i < 4; i++) {
                next = getInstructionAfter(next);
                if (next == null) break;
                println("    " + next.getAddress() + " " + next);
            }
            count++;
            if (count > 200) break;
        }
        println("FINISH count=" + count);
    }
}
