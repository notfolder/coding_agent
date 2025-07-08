#!/usr/bin/env python3
"""
Test runner for coding agent test automation
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

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Run coding agent tests')
    parser.add_argument('--unit', action='store_true', help='Run only unit tests')
    parser.add_argument('--integration', action='store_true', help='Run only integration tests')
    args = parser.parse_args()
    
    if args.unit:
        success = run_unit_tests()
    elif args.integration:
        success = run_integration_tests()
    else:
        success = run_tests()
    
    sys.exit(0 if success else 1)