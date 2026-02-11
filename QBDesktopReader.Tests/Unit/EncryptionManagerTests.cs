using System;
using System.IO;
using System.Text;
using FluentAssertions;
using Xunit;
using QBDesktopExtractor;

namespace QBDesktopReader.Tests.Unit
{
    public class EncryptionManagerTests
    {
        [Fact]
        public void GenerateKey_Returns256BitKey()
        {
            // Act
            byte[] key = EncryptionManager.GenerateKey();

            // Assert - 256 bits = 32 bytes
            key.Should().NotBeNull();
            key.Length.Should().Be(32, because: "AES-256 requires a 256-bit (32-byte) key");
        }

        [Fact]
        public void GenerateKey_ProducesCryptographicallyRandomKeys()
        {
            // Act
            byte[] key1 = EncryptionManager.GenerateKey();
            byte[] key2 = EncryptionManager.GenerateKey();

            // Assert - two generated keys should not be identical
            key1.Should().NotBeEquivalentTo(key2,
                because: "cryptographic key generation must produce unique keys");
        }

        [Fact]
        public void GenerateKey_DoesNotReturnAllZeros()
        {
            // Act
            byte[] key = EncryptionManager.GenerateKey();

            // Assert - an all-zero key would indicate RNG failure
            key.Should().Contain(b => b != 0,
                because: "a valid random key should not be all zeros");
        }

        [Fact]
        public void AlgorithmName_IsAES256CBCHmacSHA256Chunked()
        {
            // Assert
            EncryptionManager.AlgorithmName.Should().Be("AES-256-CBC-HMAC-SHA256-Chunked",
                because: "the algorithm identifier must match the server-side expectation");
        }

        [Fact]
        public void KeySize_Is256()
        {
            // Assert
            EncryptionManager.KeySize.Should().Be(256);
        }

        [Fact]
        public void GenerateKeyId_ReturnsNonEmptyString()
        {
            // Act
            string keyId = EncryptionManager.GenerateKeyId();

            // Assert
            keyId.Should().NotBeNullOrEmpty();
            keyId.Should().StartWith("key_",
                because: "key IDs follow the format key_<timestamp>_<guid>");
        }

        [Fact]
        public void GenerateKeyId_ReturnsTruncatedTo32Characters()
        {
            // Act
            string keyId = EncryptionManager.GenerateKeyId();

            // Assert
            keyId.Length.Should().Be(32,
                because: "key IDs are truncated to 32 characters");
        }

        [Fact]
        public void EncryptStreamToStream_NullInputStream_ThrowsArgumentNullException()
        {
            // Arrange
            using var output = new MemoryStream();

            // Act
            Action act = () => EncryptionManager.EncryptStreamToStream(null, output);

            // Assert
            act.Should().Throw<ArgumentNullException>()
                .Which.ParamName.Should().Be("inputStream");
        }

        [Fact]
        public void EncryptStreamToStream_NullOutputStream_ThrowsArgumentNullException()
        {
            // Arrange
            using var input = new MemoryStream(new byte[] { 1, 2, 3 });

            // Act
            Action act = () => EncryptionManager.EncryptStreamToStream(input, null);

            // Assert
            act.Should().Throw<ArgumentNullException>()
                .Which.ParamName.Should().Be("outputStream");
        }

        [Fact]
        public void EncryptStreamToStream_WithData_ProducesEncryptionResult()
        {
            // Arrange
            string plaintext = "Hello, QuickBooks migration data!";
            byte[] data = Encoding.UTF8.GetBytes(plaintext);
            using var input = new MemoryStream(data);
            using var output = new MemoryStream();

            // Act
            var result = EncryptionManager.EncryptStreamToStream(input, output);

            // Assert
            result.Should().NotBeNull();
            result.Algorithm.Should().Be(EncryptionManager.AlgorithmName);
            result.PlaintextSizeBytes.Should().Be(data.Length);
            result.EncryptedSizeBytes.Should().BeGreaterThan(0);
            result.TotalChunks.Should().BeGreaterThan(0);
            result.KeyId.Should().NotBeNullOrEmpty();
            result.DataHashSHA256.Should().NotBeNullOrEmpty();
            result.EncryptedHashSHA256.Should().NotBeNullOrEmpty();
            result.KeyBase64.Should().NotBeNullOrEmpty();
        }

        [Fact]
        public void EncryptStreamToStream_OutputContainsQBEXMagicHeader()
        {
            // Arrange
            byte[] data = Encoding.UTF8.GetBytes("test data for header check");
            using var input = new MemoryStream(data);
            using var output = new MemoryStream();

            // Act
            EncryptionManager.EncryptStreamToStream(input, output);

            // Assert - first 4 bytes should be "QBEX" magic
            byte[] outputBytes = output.ToArray();
            outputBytes.Length.Should().BeGreaterThan(4);
            Encoding.ASCII.GetString(outputBytes, 0, 4).Should().Be("QBEX",
                because: "encrypted files must start with the QBEX magic header");
        }

        [Fact]
        public void EncryptStreamToStream_EmptyInput_ProducesResultWithZeroChunks()
        {
            // Arrange
            using var input = new MemoryStream(Array.Empty<byte>());
            using var output = new MemoryStream();

            // Act
            var result = EncryptionManager.EncryptStreamToStream(input, output);

            // Assert
            result.Should().NotBeNull();
            result.PlaintextSizeBytes.Should().Be(0);
            result.TotalChunks.Should().Be(0);
        }

        [Fact]
        public void DefaultChunkSize_Is64KB()
        {
            // Assert
            EncryptionManager.DefaultChunkSize.Should().Be(64 * 1024,
                because: "the default chunk size is 64KB for streaming encryption");
        }
    }
}
