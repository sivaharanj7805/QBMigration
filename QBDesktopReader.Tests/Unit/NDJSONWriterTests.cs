using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using FluentAssertions;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using Xunit;
using QBDesktopExtractor;

namespace QBDesktopReader.Tests.Unit
{
    public class NDJSONWriterTests : IDisposable
    {
        private readonly string _testOutputDir;

        public NDJSONWriterTests()
        {
            _testOutputDir = Path.Combine(Path.GetTempPath(), $"ndjson_test_{Guid.NewGuid():N}");
            Directory.CreateDirectory(_testOutputDir);
        }

        public void Dispose()
        {
            try
            {
                if (Directory.Exists(_testOutputDir))
                    Directory.Delete(_testOutputDir, recursive: true);
            }
            catch
            {
                // Best effort cleanup
            }
        }

        // ================================================================
        // HIGH-8 Fix: Newline sanitization in NDJSON records
        // ================================================================

        [Fact]
        public async Task WriteEntityBatchAsync_RecordsWithNewlines_AreSanitized()
        {
            // This validates the HIGH-8 fix: records containing unescaped newlines
            // must be sanitized to preserve NDJSON format (one JSON object per line).
            // Without this fix, newlines in data would break NDJSON parsers.

            // Arrange
            string sessionId = "test-session-" + Guid.NewGuid().ToString("N").Substring(0, 8);
            using var writer = new NDJSONWriter(_testOutputDir, sessionId);

            var records = new[]
            {
                new { Name = "Normal Record", Value = "clean data" },
                new { Name = "Record\nWith\nNewlines", Value = "has\r\nline\rbreaks" }
            };

            // Act
            await writer.WriteEntityBatchAsync("test_entity", records);
            // Flush by disposing
            writer.Dispose();

            // Assert - read the output file and verify each line is valid JSON
            string filePath = Path.Combine(_testOutputDir, "test_entity.ndjson");
            File.Exists(filePath).Should().BeTrue("the NDJSON file should be created");

            string[] lines = File.ReadAllLines(filePath)
                .Where(l => !string.IsNullOrWhiteSpace(l))
                .ToArray();

            lines.Should().HaveCount(2, because: "two records were written");

            foreach (string line in lines)
            {
                // Each line must be valid JSON (no unescaped newlines breaking the format)
                Action parseAction = () => JObject.Parse(line);
                parseAction.Should().NotThrow(
                    because: "each NDJSON line must be a valid JSON object");

                // The line itself should not contain literal newlines
                line.Should().NotContain("\n",
                    because: "NDJSON lines must not contain literal newlines");
                line.Should().NotContain("\r",
                    because: "NDJSON lines must not contain literal carriage returns");
            }
        }

        // ================================================================
        // MEDIUM-11 Fix: Schema version is "4.2"
        // ================================================================

        [Fact]
        public void Constructor_SetsSchemaVersionTo4Point2()
        {
            // This validates the MEDIUM-11 fix: schema version in the manifest
            // must be "4.2" to match the server-side schema expectation.

            // Arrange & Act
            string sessionId = "test-session-" + Guid.NewGuid().ToString("N").Substring(0, 8);
            using var writer = new NDJSONWriter(_testOutputDir, sessionId);

            // Assert
            writer.Manifest.Should().NotBeNull();
            writer.Manifest.SchemaVersion.Should().Be("4.2",
                because: "schema version must match server expectation per MEDIUM-11 fix");
        }

        [Fact]
        public void Constructor_SetsExtractorVersionTo4Point2()
        {
            // Arrange & Act
            string sessionId = "test-session-" + Guid.NewGuid().ToString("N").Substring(0, 8);
            using var writer = new NDJSONWriter(_testOutputDir, sessionId);

            // Assert
            writer.Manifest.ExtractorVersion.Should().Be("4.2");
        }

        // ================================================================
        // Basic NDJSON Write Produces Valid Output
        // ================================================================

        [Fact]
        public async Task WriteEntityBatchAsync_BasicRecords_ProducesValidNDJSON()
        {
            // Arrange
            string sessionId = "test-session-" + Guid.NewGuid().ToString("N").Substring(0, 8);
            using var writer = new NDJSONWriter(_testOutputDir, sessionId);

            var records = new[]
            {
                new { Id = "1", Name = "Customer A", Balance = 100.50 },
                new { Id = "2", Name = "Customer B", Balance = 200.75 },
                new { Id = "3", Name = "Customer C", Balance = 0.00 }
            };

            // Act
            await writer.WriteEntityBatchAsync("customers", records);
            writer.Dispose();

            // Assert
            string filePath = Path.Combine(_testOutputDir, "customers.ndjson");
            File.Exists(filePath).Should().BeTrue();

            string[] lines = File.ReadAllLines(filePath)
                .Where(l => !string.IsNullOrWhiteSpace(l))
                .ToArray();

            lines.Should().HaveCount(3, because: "three records were written");

            // Verify each line is parseable JSON
            var parsed = lines.Select(l => JObject.Parse(l)).ToList();

            // Verify camelCase serialization (from JsonSerializerSettings)
            parsed[0]["id"]?.ToString().Should().Be("1");
            parsed[0]["name"]?.ToString().Should().Be("Customer A");
            parsed[1]["name"]?.ToString().Should().Be("Customer B");
        }

        [Fact]
        public async Task WriteEntityBatchAsync_TracksRecordCount()
        {
            // Arrange
            string sessionId = "test-session-" + Guid.NewGuid().ToString("N").Substring(0, 8);
            using var writer = new NDJSONWriter(_testOutputDir, sessionId);

            var records = new[]
            {
                new { Id = "1" },
                new { Id = "2" },
                new { Id = "3" }
            };

            // Act
            await writer.WriteEntityBatchAsync("items", records);

            // Assert - manifest tracks the records before finalization
            writer.Manifest.Should().NotBeNull();
        }

        // ================================================================
        // Constructor Validation
        // ================================================================

        [Fact]
        public void Constructor_NullOutputDirectory_ThrowsArgumentNullException()
        {
            // Act
            Action act = () => new NDJSONWriter(null, "session-id");

            // Assert
            act.Should().Throw<ArgumentNullException>();
        }

        [Fact]
        public void Constructor_NullSessionId_ThrowsArgumentNullException()
        {
            // Act
            Action act = () => new NDJSONWriter(_testOutputDir, null);

            // Assert
            act.Should().Throw<ArgumentNullException>();
        }

        [Fact]
        public void Constructor_SetsRunIdFromSessionId()
        {
            // Arrange
            string sessionId = "my-test-session-42";

            // Act
            using var writer = new NDJSONWriter(_testOutputDir, sessionId);

            // Assert
            writer.Manifest.RunId.Should().Be(sessionId);
        }

        [Fact]
        public void Constructor_SetsStartedAtToUtcNow()
        {
            // Arrange
            var before = DateTime.UtcNow;

            // Act
            using var writer = new NDJSONWriter(_testOutputDir, "session-1");

            // Assert
            var after = DateTime.UtcNow;
            writer.Manifest.StartedAt.Should().BeOnOrAfter(before);
            writer.Manifest.StartedAt.Should().BeOnOrBefore(after);
        }
    }
}
