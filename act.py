import os
import yaml
import subprocess
import xml.etree.ElementTree as ET

class GithubWorkflow:
    __TESTS_KEYWORDS = ["test", "tests", "testing"]
    __UNSUPPORTED_OS = [
        "windows-latest",
        "windows-2022",
        "windows-2019",
        "macos-13",
        "macos-13-xl",
        "macos-latest",
        "macos-12",
        "macos-latest-xl",
        "macos-12-xl",
        "macos-11"
    ]

    def __init__(self, path):
        with open(path, "r") as stream:
            self.doc = yaml.safe_load(stream)

    def __is_test(self, name):
        return any(map(lambda word: word in GithubWorkflow.__TESTS_KEYWORDS, name.split(' ')))
    
    def has_tests(self):
        try:
            if self.__is_test(self.doc["name"]):
                return True
            
            for job_name, job in self.doc['jobs'].items():
                if self.__is_test(job_name):
                    return True
                
                for step in job['steps']:
                    if self.__is_test(step['name']):
                        return True
                    
            return False                  
        except yaml.YAMLError:
            return False
            
    def remove_unsupported_os(self):
        def walk_doc(doc):
            if isinstance(doc, dict):
                for key, value in doc.items():
                    if value in GithubWorkflow.__UNSUPPORTED_OS:
                        doc[key] = "ubuntu-latest"
                    else:
                        walk_doc(value)
            elif isinstance(doc, list):
                doc[:] = filter(lambda x: x not in GithubWorkflow.__UNSUPPORTED_OS, doc)
                for value in doc:
                    walk_doc(value)

        for job_name, job in self.doc['jobs'].items():
            if 'runs-on' in job and job['runs-on'] in GithubWorkflow.__UNSUPPORTED_OS:
                job['runs-on'] = 'ubuntu-latest'
            if 'strategy' in job:
                walk_doc(job['strategy'])

    def save_yaml(self, new_path):
        with open(new_path, 'w') as file:
            yaml.dump(self.doc, file)


class JUnitXML:
    def __init__(self, folder):
        self.folder = folder

    def get_failed_tests(self):
        failed_tests = []

        for (dirpath, dirnames, filenames) in os.walk(self.folder):
            for filename in filenames:
                if filename.endswith('.xml'):
                    root = ET.parse((os.path.join(dirpath, filename))).getroot()
                    if root.tag == "testsuites":
                        testsuites = root.findall("testsuite")
                    else:
                        testsuites = [root]

                    for testsuite in testsuites:
                        for testcase in testsuite.findall("testcase"):
                            if len(testcase) == 0:
                                continue

                            failure = testcase[0]
                            if failure.tag == "failure":
                                failed_tests.append(
                                    (testcase.attrib['classname'], failure.attrib['type'], failure.attrib['message'])
                                )

        return failed_tests


class Act:
    __ACT_PATH="act"
    __FLAGS="--bind --rm"
    __DEFAULT_RUNNERS = "-P ubuntu-latest=catthehacker/ubuntu:full-latest" + \
        " -P ubuntu-22.04=catthehacker/ubuntu:act-22.04" + \
        " -P ubuntu-20.04=catthehacker/ubuntu:full-20.04" + \
        " -P ubuntu-18.04=catthehacker/ubuntu:full-18.04"

    def run_act(self, repo_path, workflows):
        command = f"cd {repo_path} &&"
        command += f"{Act.__ACT_PATH} {Act.__DEFAULT_RUNNERS} {Act.__FLAGS}"

        for workflow in workflows:
            p = subprocess.Popen(command + f" -W {workflow}", shell=True)
            code = p.wait()
            JUnitXML(os.path.join(repo_path, "target", "surefire-reports")).parse()
            #JUnitXML(os.path.join(repo_path, "target" , "surefire-reports")).parse()


act = Act()

workflow = GithubWorkflow("/home/nfsaavedra/Downloads/flacoco/.github/workflows/tests.yml")
print(workflow.has_tests())
workflow.remove_unsupported_os()
workflow.save_yaml("/home/nfsaavedra/Downloads/flacoco/.github/workflows/tests-crawler.yml")

# Needs to filter the workflows with tests
# Needs to filter OS because act only runs in ubuntu
# act.run_act("/home/nfsaavedra/Downloads/flacoco", [".github/workflows/tests.yml"])
#https://github.com/marketplace/actions/publish-test-results#generating-test-result-files