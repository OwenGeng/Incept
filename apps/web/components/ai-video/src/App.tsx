import type React from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import MainLayout from './layouts/MainLayout'
import Settings from './pages/Settings'
import NotFound from './pages/NotFound'
import ProjectLobby from './pages/aiStudio/project/ProjectLobby'
import ProjectWorkbench from './pages/aiStudio/project/ProjectWorkbench'
import RoleDetailPage from './pages/aiStudio/project/ProjectWorkbench/RoleDetailPage'
import ChapterStudio from './pages/aiStudio/chapter/ChapterStudio'
import AssetManager from './pages/aiStudio/assets/AssetManager'
import ActorAssetEditPage from './pages/aiStudio/assets/ActorAssetEditPage'
import SceneAssetEditPage from './pages/aiStudio/assets/SceneAssetEditPage'
import PropAssetEditPage from './pages/aiStudio/assets/PropAssetEditPage'
import CostumeAssetEditPage from './pages/aiStudio/assets/CostumeAssetEditPage'
import PromptTemplateManager from './pages/aiStudio/prompts/PromptTemplateManager'
import FileManager from './pages/aiStudio/files/FileManager'
import VideoEditor from './pages/aiStudio/editor/VideoEditor'
import ModelManagement from './pages/aiStudio/models/ModelManagement'
import { ChapterShotsPage } from './pages/aiStudio/shots/ChapterShotsPage'
import { ChapterShotEditPage } from './pages/aiStudio/shots/ChapterShotEditPage'

const App: React.FC = () => {
  return (
    <BrowserRouter basename="/ai-video">
      <Routes>
        <Route path="/" element={<MainLayout />}>
          <Route index element={<Navigate to="/projects" replace />} />
          <Route path="projects" element={<ProjectLobby />} />
          <Route path="projects/:projectId" element={<ProjectWorkbench />} />
          <Route path="projects/:projectId/roles/:characterId/edit" element={<RoleDetailPage />} />
          <Route path="projects/:projectId/chapters/:chapterId/prep/*" element={<Navigate to="../shots" replace />} />
          <Route path="projects/:projectId/chapters/:chapterId/studio" element={<ChapterStudio />} />
          <Route path="projects/:projectId/chapters/:chapterId/shots/:shotId/edit" element={<ChapterShotEditPage />} />
          <Route path="projects/:projectId/chapters/:chapterId/shots" element={<ChapterShotsPage />} />
          <Route path="projects/:projectId/chapters/:chapterId/prep-drafts" element={<Navigate to="../shots" replace />} />
          <Route path="projects/:projectId/editor" element={<VideoEditor />} />
          <Route path="assets" element={<AssetManager />} />
          <Route path="assets/actors/:actorImageId/edit" element={<ActorAssetEditPage />} />
          <Route path="assets/scenes/:sceneId/edit" element={<SceneAssetEditPage />} />
          <Route path="assets/props/:propId/edit" element={<PropAssetEditPage />} />
          <Route path="assets/costumes/:costumeId/edit" element={<CostumeAssetEditPage />} />
          <Route path="prompts" element={<PromptTemplateManager />} />
          <Route path="files" element={<FileManager />} />
          {/* Legacy agent-management screens only targeted removed mock APIs.
              Model configuration is the supported, persisted control surface. */}
          <Route path="agents/:id/edit" element={<Navigate to="/models" replace />} />
          <Route path="agents" element={<Navigate to="/models" replace />} />
          <Route path="models" element={<ModelManagement />} />
          <Route path="settings" element={<Settings />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
