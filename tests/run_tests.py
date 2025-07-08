#!/usr/bin/env python3
"""
Test runner for coding agent real integration tests
"""
import unittest
import sys
import os
import logging

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

def run_tests():
    """Run all tests and return results"""
    # Setup logging to suppress noise during tests
    logging.basicConfig(level=logging.CRITICAL)
    
    # Discover and run tests
    loader = unittest.TestLoader()
    start_dir = os.path.dirname(__file__)
    suite = loader.discover(start_dir, pattern='test_*.py')
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Return success status
    return result.wasSuccessful()

def run_unit_tests():
    """Run only unit tests"""
    logging.basicConfig(level=logging.CRITICAL)
    
    loader = unittest.TestLoader()
    unit_dir = os.path.join(os.path.dirname(__file__), 'unit')
    suite = loader.discover(unit_dir, pattern='test_*.py')
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()

def run_integration_tests():
    """Run only integration tests"""
    logging.basicConfig(level=logging.CRITICAL)
    
    loader = unittest.TestLoader()
    integration_dir = os.path.join(os.path.dirname(__file__), 'integration')
    suite = loader.discover(integration_dir, pattern='test_*.py')
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()

def run_real_tests():
    """Run real integration tests (requires API tokens)"""
    print("Running real integration tests...")
    print("⚠️  These tests require API tokens and will make real API calls")
    print("   Set GITHUB_TOKEN and/or GITLAB_TOKEN environment variables")
    print()
    
    # Check for API tokens
    github_token = os.environ.get('GITHUB_TOKEN')
    gitlab_token = os.environ.get('GITLAB_TOKEN')
    
    if not github_token and not gitlab_token:
        print("❌ No API tokens found. Please set GITHUB_TOKEN and/or GITLAB_TOKEN environment variables")
        return False
    
    if github_token:
        print("✅ GitHub token found - GitHub tests will run")
    else:
        print("⚠️  No GitHub token - GitHub tests will be skipped")
    
    if gitlab_token:
        print("✅ GitLab token found - GitLab tests will run")
    else:
        print("⚠️  No GitLab token - GitLab tests will be skipped")
    
    print()
    
    logging.basicConfig(level=logging.INFO)
    
    # Run the tests
    loader = unittest.TestLoader()
    start_dir = os.path.dirname(__file__)
    suite = loader.discover(start_dir, pattern='test_*.py')
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()

def run_mock_tests():
    """Run tests with mock services only"""
    print("Running mock tests...")
    logging.basicConfig(level=logging.CRITICAL)
    
    # Run tests that use mock services
    from tests.mocks.mock_llm_client import MockLLMClient
    from tests.mocks.mock_mcp_client import MockMCPToolClient
    
    # Simple test to verify mock infrastructure
    class TestMockInfrastructure(unittest.TestCase):
        def test_mock_llm_client(self):
            config = {'llm': {'provider': 'mock'}}
            client = MockLLMClient(config)
            self.assertIsNotNone(client)
        
        def test_mock_mcp_client(self):
            config = {'mcp_server_name': 'test'}
            client = MockMCPToolClient(config)
            self.assertIsNotNone(client)
    
    suite = unittest.TestLoader().loadTestsFromTestCase(TestMockInfrastructure)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Run coding agent tests')
    parser.add_argument('--unit', action='store_true', help='Run only unit tests')
    parser.add_argument('--integration', action='store_true', help='Run only integration tests')
    parser.add_argument('--real', action='store_true', help='Run real API integration tests (requires tokens)')
    parser.add_argument('--mock', action='store_true', help='Run mock tests only')
    args = parser.parse_args()
    
    if args.unit:
        success = run_unit_tests()
    elif args.integration:
        success = run_integration_tests()
    elif args.real:
        success = run_real_tests()
    elif args.mock:
        success = run_mock_tests()
    else:
        # Default: run real tests if tokens available, otherwise mock tests
        github_token = os.environ.get('GITHUB_TOKEN')
        gitlab_token = os.environ.get('GITLAB_TOKEN')
        
        if github_token or gitlab_token:
            print("API tokens detected - running real integration tests")
            success = run_real_tests()
        else:
            print("No API tokens detected - running mock tests")
            success = run_mock_tests()
    
    sys.exit(0 if success else 1)