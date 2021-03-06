# Copyright 2017 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Helper class for xctestrun file generated by prebuilt bundles."""

import glob
import logging
import os
import shutil
import tempfile

from xctestrunner.shared import bundle_util
from xctestrunner.shared import ios_constants
from xctestrunner.shared import ios_errors
from xctestrunner.shared import plist_util
from xctestrunner.shared import xcode_info_util
from xctestrunner.test_runner import dummy_project
from xctestrunner.test_runner import xcodebuild_test_executor


TESTROOT_RELATIVE_PATH = '__TESTROOT__'
_SIGNAL_TEST_WITHOUT_BUILDING_SUCCEEDED = '** TEST EXECUTE SUCCEEDED **'
_SIGNAL_TEST_WITHOUT_BUILDING_FAILED = '** TEST EXECUTE FAILED **'


class XctestRun(object):
  """Handles running test by xctestrun."""

  def __init__(self, xctestrun_file_path, test_type=None):
    """Initializes the XctestRun object.

    If arg work_dir is provided, the original app under test file and test
    bundle file will be moved to work_dir/TEST_ROOT.

    Args:
      xctestrun_file_path: string, path of the xctest run file.
      test_type: string, test type of the test bundle. See supported test types
          in module xctestrunner.shared.ios_constants.

    Raises:
      IllegalArgumentError: when the sdk or test type is not supported.
    """
    self._xctestrun_file_path = xctestrun_file_path
    self._xctestrun_file_plist_obj = plist_util.Plist(xctestrun_file_path)
    # xctestrun file always has only key at root dict.
    self._root_key = self._xctestrun_file_plist_obj.GetPlistField(
        None).keys()[0]
    self._test_type = test_type

  def SetTestEnvVars(self, env_vars):
    """Sets the additional environment variables of test's process.

    Args:
     env_vars: dict. Both key and value is string.
    """
    if not env_vars:
      return
    test_env_vars = self.GetXctestrunField('EnvironmentVariables')
    if not test_env_vars:
      test_env_vars = {}
    for key, value in env_vars.items():
      test_env_vars[key] = value
    self.SetXctestrunField('EnvironmentVariables', test_env_vars)

  def SetTestArgs(self, args):
    """Sets the additional arguments of test's process.

    Args:
     args: a list of string. Each item is an argument.
    """
    if not args:
      return
    # The generated xctest is always empty. So set it directly.
    self.SetXctestrunField('CommandLineArguments', args)

  def SetAppUnderTestEnvVars(self, env_vars):
    """Sets the additional environment variables of app under test's process.

    Args:
     env_vars: dict. Both key and value is string.
    """
    if not env_vars:
      return
    if self._test_type == ios_constants.TestType.XCUITEST:
      key = 'UITargetAppEnvironmentVariables'
    else:
      key = 'EnvironmentVariables'
    aut_env_vars = self.GetXctestrunField(key)
    if not aut_env_vars:
      aut_env_vars = {}
    for env_key, env_value in env_vars.items():
      aut_env_vars[env_key] = env_value
    self.SetXctestrunField(key, aut_env_vars)

  def SetAppUnderTestArgs(self, args):
    """Sets the additional arguments of app under test's process.

    Args:
     args: a list of string. Each item is an argument.
    """
    if not args:
      return
    if self._test_type == ios_constants.TestType.XCUITEST:
      key = 'UITargetAppCommandLineArguments'
    else:
      key = 'CommandLineArguments'
    self.SetXctestrunField(key, args)

  def SetTestsToRun(self, tests_to_run):
    """Sets the specific test methods/test classes to run in xctestrun file.

    Args:
      tests_to_run: a list of string. The format of each item is
          Test-Class-Name[/Test-Method-Name]
    """
    if not tests_to_run or tests_to_run == ['all']:
      return
    self.SetXctestrunField('OnlyTestIdentifiers', tests_to_run)

  def SetSkipTests(self, skip_tests):
    """Sets the specific test methods/test classes to skip in xctestrun file.

    Args:
      skip_tests: a list of string. The format of each item is
          Test-Class-Name[/Test-Method-Name]
    """
    if not skip_tests:
      return
    self.SetXctestrunField('SkipTestIdentifiers', skip_tests)

  def Run(self, device_id, sdk, derived_data_dir):
    """Runs the test with generated xctestrun file in the specific device.

    Args:
      device_id: ID of the device.
      sdk: shared.ios_constants.SDK, sdk of the device.
      derived_data_dir: path of derived data directory of this test session.

    Returns:
      A value of type runner_exit_codes.EXITCODE.
    """
    logging.info('Running test-without-building with device %s', device_id)
    command = ['xcodebuild', 'test-without-building',
               '-xctestrun', self._xctestrun_file_path,
               '-destination', 'id=%s' % device_id,
               '-derivedDataPath', derived_data_dir]
    exit_code, _ = xcodebuild_test_executor.XcodebuildTestExecutor(
        command,
        succeeded_signal=_SIGNAL_TEST_WITHOUT_BUILDING_SUCCEEDED,
        failed_signal=_SIGNAL_TEST_WITHOUT_BUILDING_FAILED,
        sdk=sdk,
        test_type=self.test_type,
        device_id=device_id).Execute(return_output=False)
    return exit_code

  @property
  def test_type(self):
    if not self._test_type:
      if self.HasXctestrunField('UITargetAppPath'):
        self._test_type = ios_constants.TestType.XCUITEST
      else:
        self._test_type = ios_constants.TestType.XCTEST
    return self._test_type

  def GetXctestrunField(self, field):
    """Gets the specific field in the xctestrun file.

    Args:
      field: string, the field in xctestrun file to view. A field is a list of
          keys separated by colon. E.g. Key1:Key2

    Returns:
      the object of the xctestrun file's field or None if the field does not
      exist in the plist dict.
    """
    try:
      return self._xctestrun_file_plist_obj.GetPlistField(
          '%s:%s' % (self._root_key, field))
    except ios_errors.PlistError:
      return None

  def HasXctestrunField(self, field):
    """Checks if the specific field is in the xctestrun file.

    Args:
      field: string, the field in xctestrun file to view. A field is a list of
          keys separated by colon. E.g. Key1:Key2

    Returns:
      boolean, if the specific field is in the xctestrun file.
    """
    try:
      self._xctestrun_file_plist_obj.GetPlistField(
          '%s:%s' % (self._root_key, field))
      return True
    except ios_errors.PlistError:
      return False

  def SetXctestrunField(self, field, value):
    """Sets the field with provided value in xctestrun file.

    Args:
      field: string, the field to be added in the xctestrun file. A field is a
          list of keys separated by colon. E.g. Key1:Key2
      value: a object, the value of the field to be added. It can be integer,
          bool, string, array, dict.

    Raises:
      ios_errors.PlistError: the field does not exist in the .plist file's dict.
    """
    self._xctestrun_file_plist_obj.SetPlistField(
        '%s:%s' % (self._root_key, field), value)

  def DeleteXctestrunField(self, field):
    """Deletes the field with provided value in xctestrun file.

    Args:
      field: string, the field to be added in the xctestrun file. A field is a
          list of keys separated by colon. E.g. Key1:Key2

    Raises:
      PlistError: the field does not exist in the .plist file's dict.
    """
    self._xctestrun_file_plist_obj.DeletePlistField(
        '%s:%s' % (self._root_key, field))


class XctestRunFactory(object):
  """The class to generate xctestrunfile by building dummy project."""

  def __init__(self, app_under_test_dir, test_bundle_dir,
               sdk=ios_constants.SDK.IPHONESIMULATOR,
               test_type=ios_constants.TestType.XCUITEST,
               signing_options=None, work_dir=None):
    """Initializes the XctestRun object.

    If arg work_dir is provided, the original app under test file and test
    bundle file will be moved to work_dir/TEST_ROOT.

    Args:
      app_under_test_dir: string, path of the application to be tested.
      test_bundle_dir: string, path of the test bundle.
      sdk: string, SDKRoot of the test. See supported SDKs in module
          xctestrunner.shared.ios_constants.
      test_type: string, test type of the test bundle. See supported test types
          in module xctestrunner.shared.ios_constants.
      signing_options: dict, the signing app options. See
          ios_constants.SIGNING_OPTIONS_JSON_HELP for details.
      work_dir: string, work directory which contains run files.

    Raises:
      IllegalArgumentError: when the sdk or test type is not supported.
    """
    self._app_under_test_dir = app_under_test_dir
    self._test_bundle_dir = test_bundle_dir
    self._test_name = os.path.splitext(os.path.basename(test_bundle_dir))[0]
    self._sdk = sdk
    self._test_type = test_type
    if self._sdk == ios_constants.SDK.IPHONEOS:
      self._signing_options = signing_options
    else:
      if not signing_options:
        logging.info(
            'The signing options only works on sdk iphoneos, but current sdk '
            'is %s', self._sdk)
      self._signing_options = {}
    self._work_dir = work_dir
    self._test_root_dir = None
    self._xctestrun_file_path = None
    self._xctestrun_obj = None
    self._delete_work_dir = False
    self._ValidateArguments()

  def __enter__(self):
    return self.GenerateXctestrun()

  def __exit__(self, unused_type, unused_value, unused_traceback):
    """Deletes the temp directories."""
    self.Close()

  def GenerateXctestrun(self):
    """Generates a xctestrun object according to arguments.

    The xctestrun file will be generated under work_dir/TEST_ROOT. The app under
    test and test bundle will also be moved under work_dir/TEST_ROOT.

    Returns:
      a xctestrun.XctestRun object.
    """
    if self._xctestrun_obj:
      return self._xctestrun_obj
    logging.info('Generating xctestrun file.')

    if self._work_dir:
      if not os.path.exists(self._work_dir):
        os.mkdir(self._work_dir)
    else:
      self._work_dir = tempfile.mkdtemp()
      self._delete_work_dir = True
    self._test_root_dir = os.path.join(self._work_dir, 'TEST_ROOT')
    if not os.path.exists(self._test_root_dir):
      os.mkdir(self._test_root_dir)
    # Move the app under test dir and test bundle dir into TEST_ROOT first to
    # avoid file copy later.
    # Because DummyProject._PrepareBuildProductsDir(build_productor_dir) will
    # copy both two files into build_productor_dir if the two files are not
    # there.
    if self._app_under_test_dir:
      self._app_under_test_dir = _MoveAndReplaceFile(
          self._app_under_test_dir, self._test_root_dir)
    self._test_bundle_dir = _MoveAndReplaceFile(
        self._test_bundle_dir, self._test_root_dir)
    if self._test_type == ios_constants.TestType.XCUITEST:
      self._GenerateXctestrunFileForXcuitest()
    elif self._test_type == ios_constants.TestType.XCTEST:
      self._GenerateXctestrunFileForXctest()
    elif self._test_type == ios_constants.TestType.LOGIC_TEST:
      self._GenerateXctestrunFileForLogicTest()
    # Replace the TESTROOT absolute path with __TESTROOT__ in xctestrun file.
    # Then the xctestrun file is not only used in the local machine, but also
    # other mac machines.
    with open(self._xctestrun_file_path, 'r') as xctestrun_file:
      xctestrun_file_content = xctestrun_file.read()
    xctestrun_file_content = xctestrun_file_content.replace(
        self._test_root_dir, TESTROOT_RELATIVE_PATH)
    with open(self._xctestrun_file_path, 'w+') as xctestrun_file:
      xctestrun_file.write(xctestrun_file_content)
    return self._xctestrun_obj

  def Close(self):
    """Deletes the temp directories."""
    if self._delete_work_dir and os.path.exists(self._work_dir):
      shutil.rmtree(self._work_dir)

  def _ValidateArguments(self):
    """Checks whether the arguments of this class are valid.

    Raises:
      IllegalArgumentError: when the sdk or test type is not supported.
    """
    if self._sdk not in ios_constants.SUPPORTED_SDKS:
      raise ios_errors.IllegalArgumentError(
          'The sdk %s is not supported. Supported sdks are %s.'
          % (self._sdk, ios_constants.SUPPORTED_SDKS))
    if self._test_type not in ios_constants.SUPPORTED_TEST_TYPES:
      raise ios_errors.IllegalArgumentError(
          'The test type %s is not supported. Supported test types are %s.'
          % (self._test_type, ios_constants.SUPPORTED_TEST_TYPES))
    if (self._test_type == ios_constants.TestType.LOGIC_TEST and
        self._sdk != ios_constants.SDK.IPHONESIMULATOR):
      raise ios_errors.IllegalArgumentError(
          'Only support running logic test on sdk iphonesimulator. '
          'Current sdk is %s', self._sdk)

  def _GenerateXctestrunFileForXcuitest(self):
    """Generates the xctestrun file for XCUITest.

    The approach is creating a dummy project. Run 'build-for-testing' with the
    dummy project. Then the xctestrun file and XCTRunner app template will be
    under the build products directory of dummy project's derived data dir.
    """
    dummyproject_derived_data_dir = os.path.join(self._work_dir,
                                                 'dummyproject_derived_data')
    with dummy_project.DummyProject(
        self._app_under_test_dir, self._test_bundle_dir, self._sdk,
        self._test_type, self._work_dir) as dummy_project_instance:
      if (self._signing_options and
          self._signing_options.get('xctrunner_app_provisioning_profile')):
        dummy_project_instance.SetTestBundleProvisioningProfile(
            self._signing_options.get('xctrunner_app_provisioning_profile'))
      # Use TEST_ROOT as dummy project's build products dir.
      dummy_project_instance.BuildForTesting(
          self._test_root_dir, dummyproject_derived_data_dir)

    # The basic xctestrun file and XCTRunner app are under the build products
    # directory of dummy project's derived data dir.
    # DerivedData
    #  |
    #  +--Build
    #      |
    #      +--Products
    #          |
    #          +--Debug-***
    #              |
    #              +--***-Runner.app
    #          +--***.xctestrun
    derived_data_build_products_dir = os.path.join(
        dummyproject_derived_data_dir, 'Build', 'Products')

    generated_xctrunner_app_dirs = glob.glob('%s/Debug-*/*-Runner.app' %
                                             derived_data_build_products_dir)
    if not generated_xctrunner_app_dirs:
      raise ios_errors.XctestrunError("No generated XCTRunner app was found in "
                                      "the dummy project's build products dir.")
    if len(generated_xctrunner_app_dirs) > 1:
      raise ios_errors.XctestrunError("More than one XCTRunner app were found "
                                      "in the dummy project's build products "
                                      "dir.")

    xctrunner_app_dir = os.path.join(
        self._test_root_dir, os.path.basename(generated_xctrunner_app_dirs[0]))
    shutil.move(generated_xctrunner_app_dirs[0], xctrunner_app_dir)
    if (self._signing_options and
        self._signing_options.get('xctrunner_app_enable_ui_file_sharing')):
      try:
        bundle_util.EnableUIFileSharing(xctrunner_app_dir)
      except ios_errors.BundleError as e:
        logging.warning(e.output)
    # The test bundle under XCTRunner.app/PlugIns is not actual test bundle. It
    # only contains Info.plist and _CodeSignature. So copy the real test bundle
    # under XCTRunner.app/PlugIns to replace it.
    xctrunner_plugins_dir = os.path.join(xctrunner_app_dir, 'PlugIns')
    if os.path.exists(xctrunner_plugins_dir):
      shutil.rmtree(xctrunner_plugins_dir)
    os.mkdir(xctrunner_plugins_dir)
    # The test bundle should not exist under the new generated XCTRunner.app.
    if os.path.islink(self._test_bundle_dir):
      # The test bundle under PlugIns can not be symlink since it will cause
      # app installation error.
      new_test_bundle_path = os.path.join(
          xctrunner_plugins_dir, os.path.basename(self._test_bundle_dir))
      shutil.copytree(self._test_bundle_dir, new_test_bundle_path)
      self._test_bundle_dir = new_test_bundle_path
    else:
      self._test_bundle_dir = _MoveAndReplaceFile(
          self._test_bundle_dir, xctrunner_plugins_dir)

    generated_xctestrun_file_paths = glob.glob('%s/*.xctestrun' %
                                               derived_data_build_products_dir)
    if not generated_xctestrun_file_paths:
      raise ios_errors.XctestrunError(
          "No generated xctestrun file was found in the dummy project's build "
          "products dir.")
    self._xctestrun_file_path = os.path.join(self._test_root_dir,
                                             'xctestrun.plist')
    shutil.move(generated_xctestrun_file_paths[0],
                self._xctestrun_file_path)

    self._xctestrun_obj = XctestRun(
        self._xctestrun_file_path, self._test_type)
    self._xctestrun_obj.SetXctestrunField('TestHostPath', xctrunner_app_dir)
    self._xctestrun_obj.SetXctestrunField(
        'UITargetAppPath', self._app_under_test_dir)
    self._xctestrun_obj.SetXctestrunField(
        'TestBundlePath', self._test_bundle_dir)
    # When running on iphoneos, it is necessary to remove this field.
    # For iphonesimulator, this field won't effect the test functionality. To
    # be consistent, remove this field.
    self._xctestrun_obj.DeleteXctestrunField(
        'TestingEnvironmentVariables:IDEiPhoneInternalTestBundleName')

  def _GenerateXctestrunFileForXctest(self):
    """Generates the xctestrun file for XCTest.

    The approach is creating a dummy project. Run 'build-for-testing' with the
    dummy project. Then the xctestrun file will be under the build products
    directory of dummy project's derived data dir.
    """
    dummyproject_derived_data_dir = os.path.join(self._work_dir,
                                                 'dummyproject_derived_data')
    with dummy_project.DummyProject(
        self._app_under_test_dir, self._test_bundle_dir, self._sdk,
        self._test_type, self._work_dir) as dummy_project_instance:
      # Use TEST_ROOT as dummy project's build products dir.
      dummy_project_instance.BuildForTesting(
          self._test_root_dir, dummyproject_derived_data_dir)

    app_under_test_plugins_dir = os.path.join(
        self._app_under_test_dir, 'PlugIns')
    if not os.path.exists(app_under_test_plugins_dir):
      os.mkdir(app_under_test_plugins_dir)
    new_test_bundle_path = os.path.join(
        app_under_test_plugins_dir, os.path.basename(self._test_bundle_dir))
    # The test bundle under PlugIns can not be symlink since it will cause
    # app installation error.
    if os.path.islink(self._test_bundle_dir):
      shutil.copytree(self._test_bundle_dir, new_test_bundle_path)
      self._test_bundle_dir = new_test_bundle_path
    elif new_test_bundle_path != self._test_bundle_dir:
      self._test_bundle_dir = _MoveAndReplaceFile(
          self._test_bundle_dir, app_under_test_plugins_dir)

    # The xctestrun file are under the build products directory of dummy
    # project's derived data dir.
    # DerivedData
    #  |
    #  +--Build
    #      |
    #      +--Products
    #          |
    #          +--***.xctestrun
    derived_data_build_products_dir = os.path.join(
        dummyproject_derived_data_dir, 'Build', 'Products')
    generated_xctestrun_file_paths = glob.glob('%s/*.xctestrun' %
                                               derived_data_build_products_dir)
    if not generated_xctestrun_file_paths:
      raise ios_errors.XctestrunError(
          "No generated xctestrun file was found in the dummy project's build "
          "products dir.")
    self._xctestrun_file_path = os.path.join(self._test_root_dir,
                                             'xctestrun.plist')
    shutil.move(generated_xctestrun_file_paths[0],
                self._xctestrun_file_path)
    self._xctestrun_obj = XctestRun(
        self._xctestrun_file_path, test_type=self._test_type)
    self._xctestrun_obj.SetXctestrunField(
        'TestBundlePath', self._test_bundle_dir)

  def _GenerateXctestrunFileForLogicTest(self):
    """Generates the xctestrun file for Logic Test.

    The approach is setting on xctestrun.plist directly and using `xctest` tool
    as the test host of the logic test bundle.
    """
    self._xctestrun_file_path = os.path.join(
        self._test_root_dir, 'xctestrun.plist')
    test_bundle_name = os.path.basename(self._test_bundle_dir).split('.')[0]
    plist_util.Plist(self._xctestrun_file_path).SetPlistField(
        test_bundle_name, {})
    self._xctestrun_obj = XctestRun(
        self._xctestrun_file_path, test_type=self._test_type)
    self._xctestrun_obj.SetXctestrunField(
        'TestBundlePath', self._test_bundle_dir)
    self._xctestrun_obj.SetXctestrunField(
        'TestHostPath', xcode_info_util.GetXctestToolPath(self._sdk))
    dyld_framework_path = os.path.join(
        xcode_info_util.GetSdkPlatformPath(self._sdk),
        'Developer/Library/Frameworks')
    self._xctestrun_obj.SetXctestrunField(
        'TestingEnvironmentVariables',
        {'DYLD_FRAMEWORK_PATH': dyld_framework_path,
         'DYLD_LIBRARY_PATH': dyld_framework_path})


def _MoveAndReplaceFile(src_file, target_parent_dir):
  """Moves the file under target directory and replace it if it exists."""
  new_file_path = os.path.join(
      target_parent_dir, os.path.basename(src_file))
  if os.path.exists(new_file_path):
    shutil.rmtree(new_file_path)
  shutil.move(src_file, new_file_path)
  return new_file_path
