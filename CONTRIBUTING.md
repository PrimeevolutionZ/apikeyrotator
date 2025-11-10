# Contributing to APIKeyRotator

Thank you for your interest in contributing to APIKeyRotator! 🎉 We welcome contributions from everyone, whether you're fixing a bug, adding a feature, or improving documentation.

## 📋 Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [How to Contribute](#how-to-contribute)
- [Pull Request Process](#pull-request-process)
- [Coding Standards](#coding-standards)
- [Testing Guidelines](#testing-guidelines)
- [Documentation](#documentation)
- [Release Process](#release-process)

## 🤝 Code of Conduct

By participating in this project, you agree to abide by our Code of Conduct:

- Be respectful and inclusive
- Welcome newcomers and help them get started
- Focus on what is best for the community
- Show empathy towards other community members
- Accept constructive criticism gracefully

## 🚀 Getting Started

### Prerequisites

- Python 3.9 or higher
- Git
- GitHub account
- Familiarity with Python and async programming

### Finding Ways to Contribute

1. **Browse Issues**: Check [open issues](https://github.com/PrimeevolutionZ/apikeyrotator/issues) labeled:
   - `good first issue` - Perfect for newcomers
   - `help wanted` - Community help needed
   - `bug` - Bug fixes needed
   - `enhancement` - New features or improvements

2. **Documentation**: Help improve docs, examples, or tutorials

3. **Testing**: Add test coverage or report bugs

4. **Features**: Propose new features via GitHub Discussions

## 🛠️ Development Setup

### 1. Fork and Clone

```bash
# Fork the repository on GitHub, then clone your fork
git clone https://github.com/YOUR_USERNAME/apikeyrotator.git
cd apikeyrotator

# Add upstream remote
git remote add upstream https://github.com/PrimeevolutionZ/apikeyrotator.git
```

### 2. Create Virtual Environment

```bash
# Create virtual environment
python -m venv venv

# Activate it
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
```

### 3. Install Dependencies

```bash
# Install in development mode with all dependencies
pip install -e ".[dev,test]"

# Or install manually
pip install -e .
pip install requests aiohttp python-dotenv
pip install pytest pytest-asyncio requests-mock aioresponses
pip install black flake8 mypy isort
```

### 4. Verify Installation

```bash
# Run tests to verify everything works
pytest

# Run a quick check
python -c "from apikeyrotator import APIKeyRotator; print('✅ Installation successful!')"
```

## 🎯 How to Contribute

### Reporting Bugs

Before creating a bug report:
1. Check if the bug has already been reported
2. Verify it's not a configuration issue
3. Collect relevant information

**Bug Report Template:**

```markdown
**Describe the bug**
A clear description of what the bug is.

**To Reproduce**
Steps to reproduce the behavior:
1. Initialize rotator with '...'
2. Call method '...'
3. See error

**Expected behavior**
What you expected to happen.

**Actual behavior**
What actually happened.

**Environment:**
- OS: [e.g., Windows 11, Ubuntu 22.04]
- Python version: [e.g., 3.9.7]
- APIKeyRotator version: [e.g., 0.4.1]
- Dependencies: [e.g., requests 2.28.0]

**Code snippet:**
```python
# Minimal code to reproduce the issue
from apikeyrotator import APIKeyRotator
rotator = APIKeyRotator(api_keys=["key1"])
# ...
```

**Error message:**
```
Full error traceback here
```

**Additional context**
Any other relevant information.
```

### Suggesting Features

Feature suggestions are welcome! Please use GitHub Discussions for:
- New features
- API changes
- Architectural improvements

**Feature Request Template:**

```markdown
**Problem Statement**
What problem does this feature solve?

**Proposed Solution**
How should the feature work?

**Example Usage**
```python
# Show how the feature would be used
rotator = APIKeyRotator(new_feature=True)
```

**Alternatives Considered**
What other solutions did you consider?

**Additional Context**
Any other relevant information.
```

## 📝 Pull Request Process

### 1. Create a Branch

```bash
# Update your fork
git checkout master
git pull upstream master

# Create a feature branch
git checkout -b feature/amazing-feature
# or
git checkout -b fix/bug-description
```

### Branch Naming Convention

- `feature/` - New features
- `fix/` - Bug fixes
- `docs/` - Documentation updates
- `test/` - Test improvements
- `refactor/` - Code refactoring

### 2. Make Your Changes

- Write clean, readable code
- Follow the coding standards (see below)
- Add tests for new functionality
- Update documentation as needed
- Keep commits focused and atomic

### 3. Test Your Changes

```bash
# Run all tests
pytest

# Run specific tests
pytest tests/test_rotator.py

# Run with coverage
pytest --cov=apikeyrotator --cov-report=html

# Run type checking
mypy apikeyrotator

# Run linting
flake8 apikeyrotator
black --check apikeyrotator
isort --check apikeyrotator
```

### 4. Commit Your Changes

Write clear, descriptive commit messages:

```bash
# Good commit messages
git commit -m "Add proxy rotation support to APIKeyRotator"
git commit -m "Fix rate limit detection for custom error codes"
git commit -m "Update documentation for async usage"

# Bad commit messages (avoid these)
git commit -m "Fixed bug"
git commit -m "Update"
git commit -m "Changes"
```

**Commit Message Format:**

```
<type>: <short summary>

<detailed description (optional)>

<footer (optional)>
```

Types:
- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation changes
- `test:` - Test changes
- `refactor:` - Code refactoring
- `perf:` - Performance improvements
- `chore:` - Maintenance tasks

### 5. Push and Create PR

```bash
# Push to your fork
git push origin feature/amazing-feature

# Create Pull Request on GitHub
```

**Pull Request Template:**

```markdown
## Description
Brief description of changes.

## Type of Change
- [ ] Bug fix (non-breaking change fixing an issue)
- [ ] New feature (non-breaking change adding functionality)
- [ ] Breaking change (fix or feature causing existing functionality to change)
- [ ] Documentation update

## How Has This Been Tested?
Describe the tests you ran.

## Checklist
- [ ] Code follows style guidelines
- [ ] Self-review completed
- [ ] Comments added for complex code
- [ ] Documentation updated
- [ ] Tests added/updated
- [ ] All tests pass
- [ ] No new warnings

## Related Issues
Closes #123
Relates to #456
```

### 6. Code Review

- Be responsive to feedback
- Make requested changes promptly
- Keep discussions professional and constructive
- Update your PR branch if needed:

```bash
# Update from upstream master
git checkout master
git pull upstream master
git checkout feature/amazing-feature
git rebase master
git push --force-with-lease origin feature/amazing-feature
```

## 📐 Coding Standards

### Python Style

We follow [PEP 8](https://pep8.org/) with some modifications:

```python
# Use Black for formatting (line length: 88)
black apikeyrotator

# Sort imports with isort
isort apikeyrotator

# Check with flake8
flake8 apikeyrotator
```

### Code Quality

- **Type Hints**: Use type hints for all functions

```python
from typing import List, Optional, Dict

def get_keys(api_keys: Optional[List[str]] = None) -> List[str]:
    """Get API keys from various sources."""
    pass
```

- **Docstrings**: Use Google-style docstrings

```python
def example_function(param1: str, param2: int) -> bool:
    """
    Brief description of what the function does.
    
    Args:
        param1: Description of param1
        param2: Description of param2
    
    Returns:
        Description of return value
    
    Raises:
        ValueError: When param1 is invalid
    
    Example:
        >>> example_function("test", 42)
        True
    """
    pass
```

- **Error Handling**: Use specific exceptions

```python
# ✅ Good
try:
    result = risky_operation()
except ValueError as e:
    logger.error(f"Invalid value: {e}")
    raise
except KeyError as e:
    logger.error(f"Missing key: {e}")
    raise CustomError("Operation failed") from e

# ❌ Bad
try:
    result = risky_operation()
except:
    pass
```

- **Logging**: Use appropriate log levels

```python
import logging

logger = logging.getLogger(__name__)

logger.debug("Detailed information for debugging")
logger.info("General information")
logger.warning("Warning message")
logger.error("Error message")
logger.critical("Critical error")
```

## 🧪 Testing Guidelines

### Writing Tests

- Place tests in the `tests/` directory
- Test file names: `test_<module_name>.py`
- Test function names: `test_<functionality>`

```python
import pytest
from apikeyrotator import APIKeyRotator

def test_initialization_with_keys():
    """Test that rotator initializes with provided keys."""
    rotator = APIKeyRotator(api_keys=["key1", "key2"])
    assert len(rotator.keys) == 2
    assert "key1" in rotator.keys

def test_get_request_success(requests_mock):
    """Test successful GET request."""
    requests_mock.get("http://example.com", json={"status": "ok"})
    rotator = APIKeyRotator(api_keys=["key1"])
    response = rotator.get("http://example.com")
    assert response.status_code == 200
```

### Test Categories

1. **Unit Tests**: Test individual functions/methods
2. **Integration Tests**: Test component interactions
3. **Async Tests**: Test async functionality

```python
@pytest.mark.asyncio
async def test_async_get_request():
    """Test async GET request."""
    async with AsyncAPIKeyRotator(api_keys=["key1"]) as rotator:
        response = await rotator.get("http://example.com")
        assert response.status == 200
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=apikeyrotator --cov-report=html

# Run specific test file
pytest tests/test_rotator.py

# Run specific test
pytest tests/test_rotator.py::test_initialization_with_keys

# Run tests matching pattern
pytest -k "test_async"

# Run with verbose output
pytest -v

# Stop on first failure
pytest -x
```

## 📚 Documentation

### Documentation Types

1. **Code Documentation**: Docstrings in code
2. **API Documentation**: In `docs/API_REFERENCE.md`
3. **User Guides**: In `docs/` directory
4. **Examples**: In `docs/EXAMPLES.md`
5. **README**: Project overview

### Writing Documentation

- Use clear, simple language
- Include code examples
- Keep examples short and focused
- Test all code examples
- Use proper Markdown formatting

## 🚢 Release Process

Releases are managed by maintainers. The process:

1. **Version Bump**: Update version in `setup.py`
2. **Changelog**: Update `CHANGELOG.md`
3. **Testing**: Run full test suite
4. **Tag**: Create git tag: `git tag v0.4.2`
5. **Push**: Push tag: `git push origin v0.4.2`
6. **Release**: Create GitHub release
7. **PyPI**: Publish to PyPI

### Version Numbering

We follow [Semantic Versioning](https://semver.org/):

- **MAJOR**: Incompatible API changes
- **MINOR**: New features (backward compatible)
- **PATCH**: Bug fixes (backward compatible)

Example: `0.4.1` → `0.5.0` (new feature) or `0.4.2` (bug fix)

## 🎯 Development Tips

### Setting Up IDE

**VS Code:**

`.vscode/settings.json`:
```json
{
  "python.linting.enabled": true,
  "python.linting.pylintEnabled": false,
  "python.linting.flake8Enabled": true,
  "python.formatting.provider": "black",
  "editor.formatOnSave": true,
  "python.testing.pytestEnabled": true
}
```

**PyCharm:**
- Enable "Black" as code formatter
- Enable pytest as test runner
- Configure flake8 as external tool

### Debugging

```python
# Add debug logging
import logging
logging.basicConfig(level=logging.DEBUG)

# Use pdb for debugging
import pdb; pdb.set_trace()

# Or use built-in breakpoint()
breakpoint()
```

### Common Tasks

```bash
# Format code
black apikeyrotator tests

# Sort imports
isort apikeyrotator tests

# Run linting
flake8 apikeyrotator

# Type checking
mypy apikeyrotator

# Run tests with coverage
pytest --cov=apikeyrotator --cov-report=html

# Build documentation
# (if we add Sphinx later)
cd docs && make html
```

## 🏆 Recognition

Contributors are recognized in:
- Project README
- Release notes
- Contributors page

Significant contributors may be invited to join the maintenance team.

## 📞 Getting Help

- **Questions**: Use [GitHub Discussions](https://github.com/PrimeevolutionZ/apikeyrotator/discussions)
- **Chat**: Join our community (link TBD)
- **Email**: develop@eclips-team.ru

## 📜 License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

<div align="center">

**Thank you for contributing to APIKeyRotator! 🎉**

Made with ❤️ by [Eclips Team](https://github.com/PrimeevolutionZ)

</div>