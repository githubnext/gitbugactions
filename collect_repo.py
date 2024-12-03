import datetime
import json
import logging
import os
from pathlib import Path
import sys
import tempfile
import traceback
import uuid

import fire

from github import Github, Repository
from gitbugactions.util import delete_repo_clone, clone_repo
from gitbugactions.crawler import RepoStrategy, RepoCrawler
from gitbugactions.actions.actions import (
    GitHubActions,
    ActCacheDirManager,
    ActCheckCodeFailureStrategy,
)
from gitbugactions.infra.infra_checkers import is_infra_file


class CollectReposStatic(RepoStrategy):
    def __init__(self, data_path: str):
        self.data_path = data_path
        self.uuid = str(uuid.uuid1())

    def save_data(self, data: dict, repo):
        """
        Saves the data json to a file with the name of the repository
        """
        repo_name = repo.full_name.replace("/", "-")
        data_path = os.path.join(self.data_path, repo_name + ".json")
        with open(data_path, "w") as f:
            json.dump(data, f, indent=4)

    def handle_repo(self, repo: Repository):
        logging.info(f"Cloning {repo.full_name} - {repo.clone_url}")
        repo_path = os.path.join(tempfile.gettempdir(), self.uuid, repo.full_name.replace("/", "-"))

        data = {
            "repository": repo.full_name,
            "stars": repo.stargazers_count,
            "language": repo.language.strip().lower(),
            "size": repo.size,
            "clone_url": repo.clone_url,
            "timestamp": datetime.datetime.now(datetime.UTC).isoformat() + "Z",
            "clone_success": False,
            "number_of_actions": 0,
            "number_of_test_actions": 0,
            "actions_successful": False,
        }

        repo_clone = clone_repo(repo.clone_url, repo_path)
        try:
            data["clone_success"] = True

            actions = GitHubActions(repo_path, repo.language)
            data["number_of_actions"] = len(actions.workflows)
            data["actions_build_tools"] = [x.get_build_tool() for x in actions.workflows]
            data["number_of_test_actions"] = len(actions.test_workflows)
            data["actions_test_build_tools"] = [x.get_build_tool() for x in actions.test_workflows]
            actions.save_workflows()

            print(data)
            print(len(actions.test_workflows))
            if len(actions.test_workflows) == 1:
                logging.info(f"Running actions for {repo.full_name}")
                # Act creates names for the containers by hashing the content of the workflows
                # To avoid conflicts between threads, we randomize the name
                actions.test_workflows[0].doc["name"] = str(uuid.uuid4())
                actions.save_workflows()

                logging.warning(f"Skipping running")
                return
                act_cache_dir = ActCacheDirManager.acquire_act_cache_dir()
                try:
                    act_run = actions.run_workflow(
                        actions.test_workflows[0], act_cache_dir=act_cache_dir
                    )
                finally:
                    ActCacheDirManager.return_act_cache_dir(act_cache_dir)

                data["actions_successful"] = not act_run.failed
                data["actions_run"] = act_run.asdict()

            delete_repo_clone(repo_clone)
            self.save_data(data, repo)
        except Exception as e:
            logging.error(f"Error while processing {repo.full_name}: {traceback.format_exc()}")

            delete_repo_clone(repo_clone)
            self.save_data(data, repo)


def collect_repo(owner_repo: str, out_path: str | Path = "./out/"):
    """Collect the repositories from GitHub that match the query and have executable
    GitHub Actions workflows with parsable tests.

    Args:
        owner_repo (str): owner/repo
        out_path (str, optional): Folder on which the results will be saved. Defaults to "./out/".
    """
    if "/" not in owner_repo:
        raise ValueError("owner_repo must be in the format owner/repo")
    out_path = Path(out_path)
    out_path.mkdir(parents=True, exist_ok=True)

    logging.info(f"Collecting info for {owner_repo}")
    github_client = Github()
    repo = github_client.get_repo(owner_repo)

    logging.info(f"Running repo {owner_repo}")
    collector = CollectReposStatic(out_path)
    collector.handle_repo(repo)


def main():
    fire.Fire(collect_repo)


if __name__ == "__main__":
    sys.exit(main())
