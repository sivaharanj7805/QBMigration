using System;
using FluentAssertions;
using Xunit;
using QBDesktopExtractor;

namespace QBDesktopReader.Tests.Unit
{
    public class LogRedactorTests
    {
        private readonly LogRedactor _redactor;

        public LogRedactorTests()
        {
            _redactor = new LogRedactor(RedactionConfig.Default);
        }

        // ================================================================
        // API Key Redaction
        // ================================================================

        [Fact]
        public void Redact_ApiKeyInJsonFormat_IsRedacted()
        {
            // Arrange
            string input = "{\"api_key\": \"sk-abc123def456ghi789\"}";

            // Act
            string result = _redactor.Redact(input);

            // Assert
            result.Should().Contain("[REDACTED]");
            result.Should().NotContain("sk-abc123def456ghi789");
        }

        [Fact]
        public void Redact_ApiKeyInKeyValueFormat_IsRedacted()
        {
            // Arrange
            string input = "api_key=my-secret-api-key-12345";

            // Act
            string result = _redactor.Redact(input);

            // Assert
            result.Should().Contain("[REDACTED]");
            result.Should().NotContain("my-secret-api-key-12345");
        }

        [Fact]
        public void Redact_SecretKeyInJson_IsRedacted()
        {
            // Arrange
            string input = "{\"secret_key\": \"very-secret-value\"}";

            // Act
            string result = _redactor.Redact(input);

            // Assert
            result.Should().Contain("[REDACTED]");
            result.Should().NotContain("very-secret-value");
        }

        // ================================================================
        // Bearer Token Redaction
        // ================================================================

        [Fact]
        public void Redact_BearerToken_IsRedacted()
        {
            // Arrange
            string input = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test";

            // Act
            string result = _redactor.Redact(input);

            // Assert
            result.Should().Contain("[REDACTED]");
            result.Should().NotContain("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9");
        }

        [Fact]
        public void Redact_BearerInKeyValueFormat_IsRedacted()
        {
            // Arrange
            string input = "Bearer=some-token-value-here";

            // Act
            string result = _redactor.Redact(input);

            // Assert
            result.Should().Contain("[REDACTED]");
            result.Should().NotContain("some-token-value-here");
        }

        // ================================================================
        // MEDIUM-6 Fix: Legitimate "key" fields NOT redacted
        // ================================================================

        [Fact]
        public void Redact_LegitimateKeyBusinessField_IsNotRedacted()
        {
            // This validates the MEDIUM-6 fix: bare "key" in JSON should NOT be
            // redacted because it matches legitimate business data like
            // {"key": "AccountType"} or {"key": "CustomerName"}.
            // Only compound names like "api_key" or "secret_key" should be redacted.

            // Arrange
            string input = "{\"key\": \"AccountType\"}";

            // Act
            string result = _redactor.Redact(input);

            // Assert - the value "AccountType" should survive redaction
            result.Should().Contain("AccountType",
                because: "bare 'key' field is legitimate business data per MEDIUM-6 fix");
        }

        [Fact]
        public void Redact_LegitimateKeyFieldInLog_IsNotRedacted()
        {
            // Arrange
            string input = "Processing record with key: Invoice-12345";

            // Act
            string result = _redactor.Redact(input);

            // Assert - "Invoice-12345" should not be treated as a secret
            result.Should().Contain("Invoice-12345",
                because: "bare 'key' in log context is not a secret");
        }

        [Fact]
        public void Redact_ApiKeyVsBarKey_OnlyApiKeyRedacted()
        {
            // Arrange - both bare "key" and "api_key" in same message
            string inputApiKey = "{\"api_key\": \"secret-value-123\"}";
            string inputBareKey = "{\"key\": \"AccountType\"}";

            // Act
            string resultApiKey = _redactor.Redact(inputApiKey);
            string resultBareKey = _redactor.Redact(inputBareKey);

            // Assert
            resultApiKey.Should().NotContain("secret-value-123",
                because: "api_key IS a secret and should be redacted");
            resultBareKey.Should().Contain("AccountType",
                because: "bare key is NOT a secret and should be preserved");
        }

        // ================================================================
        // SSN Redaction
        // ================================================================

        [Fact]
        public void Redact_SSNWithDashes_IsRedacted()
        {
            // Arrange
            string input = "Employee SSN: 123-45-6789";

            // Act
            string result = _redactor.Redact(input);

            // Assert
            result.Should().Contain("[SSN]");
            result.Should().NotContain("123-45-6789");
        }

        [Fact]
        public void Redact_SSNStandardFormat_IsRedacted()
        {
            // Arrange - standalone XXX-XX-XXXX format
            string input = "Record contains 123-45-6789 as identifier";

            // Act
            string result = _redactor.Redact(input);

            // Assert
            result.Should().Contain("[SSN]");
            result.Should().NotContain("123-45-6789");
        }

        [Fact]
        public void Redact_SSNWithContextPrefix_IsRedacted()
        {
            // Arrange
            string input = "Social Security Number: 123456789";

            // Act
            string result = _redactor.Redact(input);

            // Assert
            result.Should().Contain("[SSN]");
            result.Should().NotContain("123456789");
        }

        // ================================================================
        // Empty / Null Input Handling
        // ================================================================

        [Fact]
        public void Redact_NullInput_ReturnsNull()
        {
            // Act
            string result = _redactor.Redact(null);

            // Assert
            result.Should().BeNull();
        }

        [Fact]
        public void Redact_EmptyString_ReturnsEmptyString()
        {
            // Act
            string result = _redactor.Redact(string.Empty);

            // Assert
            result.Should().BeEmpty();
        }

        [Fact]
        public void Redact_PlainTextWithNoSensitiveData_ReturnsUnchanged()
        {
            // Arrange
            string input = "Extracted 150 customer records successfully";

            // Act
            string result = _redactor.Redact(input);

            // Assert
            result.Should().Be(input);
        }

        // ================================================================
        // Disabled Redaction
        // ================================================================

        [Fact]
        public void Redact_WhenDisabled_ReturnsOriginalMessage()
        {
            // Arrange
            var disabledRedactor = new LogRedactor(RedactionConfig.Disabled);
            string input = "api_key=super-secret-value, SSN: 123-45-6789";

            // Act
            string result = disabledRedactor.Redact(input);

            // Assert
            result.Should().Be(input,
                because: "redaction is disabled and the message should pass through unchanged");
        }

        // ================================================================
        // Password Redaction
        // ================================================================

        [Fact]
        public void Redact_PasswordInJson_IsRedacted()
        {
            // Arrange
            string input = "{\"password\": \"P@ssw0rd123!\"}";

            // Act
            string result = _redactor.Redact(input);

            // Assert
            result.Should().Contain("[REDACTED]");
            result.Should().NotContain("P@ssw0rd123!");
        }
    }
}
