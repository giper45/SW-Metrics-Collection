import com.github.javaparser.JavaParser;
import com.github.javaparser.ParseResult;
import com.github.javaparser.ParserConfiguration;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.PackageDeclaration;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import com.github.javaparser.ast.body.EnumDeclaration;
import com.github.javaparser.ast.body.RecordDeclaration;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.stream.Stream;

public final class JavaInventoryTool {
    private JavaInventoryTool() {
    }

    public static void main(String[] args) throws Exception {
        Path root = parseRoot(args);
        Inventory inventory = collect(root);
        System.out.print(inventory.toJson());
    }

    private static Path parseRoot(String[] args) {
        for (int i = 0; i < args.length - 1; i++) {
            if ("--root".equals(args[i])) {
                return Path.of(args[i + 1]);
            }
        }
        throw new IllegalArgumentException("missing --root <path>");
    }

    private static Inventory collect(Path root) throws IOException {
        ParserConfiguration configuration = new ParserConfiguration();
        configuration.setLanguageLevel(ParserConfiguration.LanguageLevel.BLEEDING_EDGE);
        JavaParser parser = new JavaParser(configuration);

        List<Path> javaFiles = new ArrayList<>();
        try (Stream<Path> stream = Files.walk(root)) {
            stream
                .filter(Files::isRegularFile)
                .filter(path -> path.toString().endsWith(".java"))
                .sorted(Comparator.naturalOrder())
                .forEach(javaFiles::add);
        }

        Inventory inventory = new Inventory();
        inventory.filesScanned = javaFiles.size();

        for (Path javaFile : javaFiles) {
            ParseResult<CompilationUnit> result = parser.parse(javaFile);
            if (!result.isSuccessful() || result.getResult().isEmpty()) {
                inventory.parseErrors++;
                continue;
            }

            CompilationUnit unit = result.getResult().get();
            inventory.classCount += unit.findAll(ClassOrInterfaceDeclaration.class)
                .stream()
                .filter(declaration -> !declaration.isInterface())
                .count();
            inventory.interfaceCount += unit.findAll(ClassOrInterfaceDeclaration.class)
                .stream()
                .filter(ClassOrInterfaceDeclaration::isInterface)
                .count();
            inventory.enumCount += unit.findAll(EnumDeclaration.class).size();
            inventory.recordCount += unit.findAll(RecordDeclaration.class).size();

            Optional<PackageDeclaration> packageDeclaration = unit.getPackageDeclaration();
            if (packageDeclaration.isPresent()) {
                String packageName = packageDeclaration.get().getNameAsString().trim();
                if (!packageName.isEmpty()) {
                    inventory.packages.add(packageName);
                } else {
                    inventory.unnamedPackageFiles++;
                }
            } else {
                inventory.unnamedPackageFiles++;
            }
        }

        return inventory;
    }

    private static final class Inventory {
        long filesScanned;
        long classCount;
        long recordCount;
        long interfaceCount;
        long enumCount;
        long parseErrors;
        long unnamedPackageFiles;
        final Set<String> packages = new LinkedHashSet<>();

        String toJson() {
            return "{"
                + "\"files_scanned\":" + filesScanned + ","
                + "\"class_count\":" + classCount + ","
                + "\"record_count\":" + recordCount + ","
                + "\"interface_count\":" + interfaceCount + ","
                + "\"enum_count\":" + enumCount + ","
                + "\"package_count\":" + packages.size() + ","
                + "\"unnamed_package_files\":" + unnamedPackageFiles + ","
                + "\"parse_errors\":" + parseErrors
                + "}";
        }
    }
}
