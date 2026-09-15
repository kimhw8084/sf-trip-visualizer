import Foundation
import Translation

@main
struct LocalTranslator {
    static func main() async throws {
        guard CommandLine.arguments.count == 5 else {
            fputs("usage: translate_local input.json output.json source_language target_language\n", stderr)
            exit(2)
        }
        let input = URL(fileURLWithPath: CommandLine.arguments[1])
        let output = URL(fileURLWithPath: CommandLine.arguments[2])
        let strings = try JSONDecoder().decode([String].self, from: Data(contentsOf: input))
        let session = TranslationSession(
            installedSource: Locale.Language(identifier: CommandLine.arguments[3]),
            target: Locale.Language(identifier: CommandLine.arguments[4])
        )
        var translations: [String: String] = [:]
        for start in stride(from: 0, to: strings.count, by: 24) {
            let batch = Array(strings[start..<min(start + 24, strings.count)])
            let requests = batch.enumerated().map {
                TranslationSession.Request(sourceText: $0.element, clientIdentifier: String($0.offset))
            }
            let responses = try await session.translations(from: requests)
            for (source, response) in zip(batch, responses) {
                translations[source] = response.targetText
            }
            print("translated \(min(start + 24, strings.count))/\(strings.count)")
        }
        let data = try JSONSerialization.data(withJSONObject: translations, options: [.prettyPrinted, .sortedKeys])
        try data.write(to: output)
    }
}
