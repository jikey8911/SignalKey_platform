
import unittest
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from api.tests.test_end_to_end import TestEndToEnd

if __name__ == '__main__':
    suite = unittest.TestSuite()
    suite.addTest(TestEndToEnd('test_train_and_predict_flow'))
    
    with open('test_output.txt', 'w') as f:
        runner = unittest.TextTestRunner(stream=f, verbosity=2)
        result = runner.run(suite)
        
    if not result.wasSuccessful():
        sys.exit(1)
