import warnings

try:
    from pyparsing.warnings import PyparsingWarning
except ImportError:
    pass
else:
    # pydot still calls pre-PEP8 pyparsing APIs; pyparsing 3.3+ raises these under PYTHONWARNINGS=error.
    warnings.filterwarnings("ignore", category=PyparsingWarning)
