#pragma once
#include <drogon/HttpController.h>

namespace blackkeys::assetsbo::handling::event {
class Events : public drogon::HttpController<Events> {
public:
  METHOD_LIST_BEGIN
  ADD_METHOD_TO(Events::EventsList, "/v1/event/list", drogon::Get);
  ADD_METHOD_TO(Events::EventsCreate, "/v1/event/create", drogon::Get,
                drogon::Post);
  ADD_METHOD_TO(Events::EventsDetails, "/v1/event/{title}/details",
                drogon::Get);
  ADD_METHOD_TO(Events::EventsUpdate, "/v1/event/{title}/update", drogon::Get,
                drogon::Post);
  ADD_METHOD_TO(Events::EventsDelete, "/v1/event/{title}/delete", drogon::Post);
  ADD_METHOD_TO(Events::EventsImage, "/v1/event/{title}/image", drogon::Get);
  METHOD_LIST_END
  using Callback = std::function<void(const drogon::HttpResponsePtr &)>;
  void EventsList(const drogon::HttpRequestPtr &, Callback &&);
  void EventsCreate(const drogon::HttpRequestPtr &, Callback &&);
  void EventsDetails(const drogon::HttpRequestPtr &, Callback &&,
                     std::string title);
  void EventsUpdate(const drogon::HttpRequestPtr &, Callback &&,
                    std::string title);
  void EventsDelete(const drogon::HttpRequestPtr &, Callback &&,
                    std::string title);
  void EventsImage(const drogon::HttpRequestPtr &, Callback &&,
                   std::string title);
};
} // namespace blackkeys::assetsbo::handling::event
