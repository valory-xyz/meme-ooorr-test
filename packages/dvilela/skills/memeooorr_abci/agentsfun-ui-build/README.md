# Agents.fun UI

React application for Agents.fun UI, designed to be consumed by the agent and available in [Pearl](https://github.com/olas-operate-app).

## 🧪 Mock Data
To mock, update the `IS_MOCK_ENABLED` in `.env` and the app will use the mock data instead of the API. 

## 🗜️ Zip locally

1. Run the build command: `yarn nx run agentsfun-ui:build`
2. Navigate to the build output directory: `cd dist/apps/agentsfun-ui`
3. Create a zip archive of the build artifacts: `zip -r ../../../agentsfun-ui-build.zip .`

## 📦 Release process

1. Bump the version in `package.json`
2. Push a new tag to the repository, (e.g., `v1.0.0-agentsfun`)
3. The CI will build and release the contents of the `dist/apps/agentsfun-ui` directory to a zip file.
